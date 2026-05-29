# Author: xhico
# Date: May 27, 2026
"""
Read-only dashboard endpoints for the finance app.

These aggregate the imported data for the dashboards: income, expenses,
cashflow, accounts, balance snapshots and a filterable transactions list.
"""

import tempfile
from datetime import date

from django.db.models import Q, Sum
from django.db.models.functions import TruncMonth
from rest_framework.generics import ListAPIView, RetrieveUpdateAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from finance.models import (
    Account,
    BalanceSnapshot,
    Category,
    CategoryRule,
    IgnoreRule,
    PortfolioSnapshot,
    StatementImport,
    Transaction,
)
from finance.parsers import extract_text
from finance.serializers import (
    AccountBriefSerializer,
    CategoryBriefSerializer,
    PortfolioSnapshotSerializer,
    TransactionSerializer,
)
from finance.services import import_degiro_csv, import_statement


def _quarter(month):
    """
    Return the calendar quarter label for a month.

    Args:
        month (datetime.date): The first day of the month

    Returns:
        str: A label such as "2026-Q2"
    """

    return f"{month.year}-Q{(month.month - 1) // 3 + 1}"


def _month_key(d):
    """
    Return the YYYY-MM label for a date.

    Args:
        d (datetime.date): Any date

    Returns:
        str: The month label
    """

    return d.strftime("%Y-%m")


# Category kinds that count as money out for the dashboards
EXPENSE_KINDS = (Category.Kind.EXPENSE, Category.Kind.TAX)


def _income_series(scope=None):
    """
    Compute monthly + quarterly income totals for one scope.

    Args:
        scope (str | None): "personal", "business", or None for everything

    Returns:
        dict: {"monthly": [...], "quarterly": [...]}
    """

    base = Transaction.objects.filter(category__kind=Category.Kind.INCOME)
    if scope:
        base = base.filter(account__scope=scope)
    rows = base.annotate(month=TruncMonth("date")).values("month").annotate(total=Sum("amount")).order_by("month")
    monthly = [{"period": _month_key(r["month"]), "income": float(r["total"])} for r in rows]
    quarters = {}
    for r in rows:
        q = _quarter(r["month"])
        quarters[q] = quarters.get(q, 0.0) + float(r["total"])
    quarterly = [{"period": q, "income": total} for q, total in sorted(quarters.items())]
    return {"monthly": monthly, "quarterly": quarterly}


class IncomeView(APIView):
    """
    Monthly and quarterly income broken down by scope.

    - Three series in one response: all, business, personal
    """

    def get(self, request):
        """
        Return the income series for each scope.

        Args:
            request (Request): The incoming request

        Returns:
            Response: A dict with keys "all", "business" and "personal"
        """

        return Response(
            {
                "all": _income_series(),
                "business": _income_series(scope="business"),
                "personal": _income_series(scope="personal"),
            }
        )


def _expenses_series(scope=None):
    """
    Compute expense aggregates for one scope.

    Args:
        scope (str | None): "personal", "business", or None for everything

    Returns:
        dict: {"monthly": [...], "by_category": [...], "monthly_by_category": [...]}
    """

    base = Transaction.objects.filter(category__kind__in=EXPENSE_KINDS)
    if scope:
        base = base.filter(account__scope=scope)

    monthly_rows = (
        base.annotate(month=TruncMonth("date")).values("month").annotate(total=Sum("amount")).order_by("month")
    )
    monthly = [{"period": _month_key(r["month"]), "total": -float(r["total"])} for r in monthly_rows]

    by_cat_rows = base.values("category__name", "category__kind").annotate(total=Sum("amount")).order_by("total")
    by_category = [
        {"category": r["category__name"], "kind": r["category__kind"], "total": -float(r["total"])} for r in by_cat_rows
    ]

    mc_rows = (
        base.annotate(month=TruncMonth("date"))
        .values("month", "category__name")
        .annotate(total=Sum("amount"))
        .order_by("month", "category__name")
    )
    monthly_by_category = [
        {
            "period": _month_key(r["month"]),
            "category": r["category__name"],
            "total": -float(r["total"]),
        }
        for r in mc_rows
    ]

    return {"monthly": monthly, "by_category": by_category, "monthly_by_category": monthly_by_category}


class ExpensesView(APIView):
    """
    Expense aggregates broken down by scope.

    - Three series in one response: all, business, personal
    - Amounts are returned as positive numbers so charts plot upwards
    """

    def get(self, request):
        """
        Return the expense aggregates for each scope.

        Args:
            request (Request): The incoming request

        Returns:
            Response: A dict with keys "all", "business" and "personal"
        """

        return Response(
            {
                "all": _expenses_series(),
                "business": _expenses_series("business"),
                "personal": _expenses_series("personal"),
            }
        )


def _investments_series(scope=None):
    """
    Compute investment flows and cumulative invested for one scope.

    "Invested" treats outflows (negative amounts) as money put into the
    investment account and inflows as money pulled back out, so net invested is
    just minus the signed sum.

    Args:
        scope (str | None): "personal", "business", or None for everything

    Returns:
        dict: {"monthly": [...], "cumulative": [...], "by_category": [...]}
    """

    base = Transaction.objects.filter(category__kind=Category.Kind.INVESTMENT)
    if scope:
        base = base.filter(account__scope=scope)

    # Sum signed amounts per month, then split into invested (outflow) and
    # returned (inflow) using a second pass to keep the SQL simple
    rows = base.annotate(month=TruncMonth("date")).values("month").annotate(total=Sum("amount")).order_by("month")
    monthly_net = {_month_key(r["month"]): -float(r["total"]) for r in rows}

    out_rows = (
        base.filter(amount__lt=0).annotate(month=TruncMonth("date")).values("month").annotate(total=Sum("amount"))
    )
    in_rows = base.filter(amount__gt=0).annotate(month=TruncMonth("date")).values("month").annotate(total=Sum("amount"))
    invested_by_month = {_month_key(r["month"]): -float(r["total"]) for r in out_rows}
    returned_by_month = {_month_key(r["month"]): float(r["total"]) for r in in_rows}

    months = sorted(monthly_net)
    monthly = []
    cumulative = []
    running = 0.0
    for m in months:
        invested = invested_by_month.get(m, 0.0)
        returned = returned_by_month.get(m, 0.0)
        net = monthly_net[m]
        running += net
        monthly.append({"period": m, "invested": invested, "returned": returned, "net": net})
        cumulative.append({"period": m, "total": running})

    by_cat = base.values("category__name").annotate(total=Sum("amount")).order_by("total")
    by_category = [{"category": r["category__name"], "net_invested": -float(r["total"])} for r in by_cat]

    # Valuation block: the latest manually-entered portfolio snapshot across
    # the brokerage accounts in scope, plus a small history series for the
    # frontend to chart value vs cost basis.
    snapshots = PortfolioSnapshot.objects.filter(account__kind=Account.Kind.BROKERAGE)
    if scope:
        snapshots = snapshots.filter(account__scope=scope)

    history_rows = snapshots.values("as_of").annotate(total=Sum("market_value")).order_by("as_of")
    history = [{"as_of": r["as_of"].isoformat(), "market_value": float(r["total"])} for r in history_rows]
    net_invested = running
    if history:
        latest = history[-1]
        current_value = latest["market_value"]
        valuation = {
            "current_value": current_value,
            "as_of": latest["as_of"],
            "unrealised": current_value - net_invested,
            "history": history,
        }
    else:
        valuation = {"current_value": None, "as_of": None, "unrealised": None, "history": []}

    return {
        "monthly": monthly,
        "cumulative": cumulative,
        "by_category": by_category,
        "net_invested": net_invested,
        "valuation": valuation,
    }


class InvestmentsView(APIView):
    """
    Investment flows broken down by scope.

    - Three series in one response: all, business, personal
    - Net invested is signed so the cumulative line trends upward as money
      goes out to the investment account
    """

    def get(self, request):
        """
        Return the investment series for each scope.

        Args:
            request (Request): The incoming request

        Returns:
            Response: A dict with keys "all", "business" and "personal"
        """

        # Expose the brokerage accounts so the frontend can populate the
        # "set current value" picker without a second round-trip
        brokerage_accounts = AccountBriefSerializer(
            Account.objects.filter(kind=Account.Kind.BROKERAGE).order_by("name"), many=True
        ).data

        return Response(
            {
                "all": _investments_series(),
                "business": _investments_series("business"),
                "personal": _investments_series("personal"),
                "brokerage_accounts": brokerage_accounts,
            }
        )


def _cashflow_series(scope=None):
    """
    Compute the monthly income / expenses / net series for one scope.

    Args:
        scope (str | None): "personal", "business", or None for everything

    Returns:
        list[dict]: One entry per month, oldest first
    """

    base = Transaction.objects.all()
    if scope:
        base = base.filter(account__scope=scope)

    # Sum income credits per month
    inc_rows = (
        base.filter(category__kind=Category.Kind.INCOME)
        .annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(total=Sum("amount"))
    )
    # Sum expense and tax debits per month
    exp_rows = (
        base.filter(category__kind__in=EXPENSE_KINDS)
        .annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(total=Sum("amount"))
    )

    # Merge the two streams on the month key
    bucket = {}
    for r in inc_rows:
        key = _month_key(r["month"])
        bucket.setdefault(key, {"income": 0.0, "expenses": 0.0})
        bucket[key]["income"] = float(r["total"])
    for r in exp_rows:
        key = _month_key(r["month"])
        bucket.setdefault(key, {"income": 0.0, "expenses": 0.0})
        # Store expenses as a positive magnitude
        bucket[key]["expenses"] = -float(r["total"])

    series = []
    for key in sorted(bucket):
        row = bucket[key]
        row["period"] = key
        row["net"] = row["income"] - row["expenses"]
        series.append(row)
    return series


class CashflowView(APIView):
    """
    Monthly net cashflow (income minus expenses), broken down by scope.

    - Three series in one response: all, business and personal
    - Internal transfers and investments are excluded from in / out totals
    """

    def get(self, request):
        """
        Return the cashflow series for each scope.

        Args:
            request (Request): The incoming request

        Returns:
            Response: A dict with keys "all", "business" and "personal", each
            mapping to a list of monthly income / expenses / net entries
        """

        return Response(
            {
                "all": _cashflow_series(),
                "business": _cashflow_series(scope="business"),
                "personal": _cashflow_series(scope="personal"),
            }
        )


def _account_balance_at(account, on_date):
    """
    Return the running balance of an account on or before a given date.

    Args:
        account (Account): The account to inspect
        on_date (datetime.date): The cut-off date

    Returns:
        float: The latest known balance, or 0 when the account has no movements
    """

    last = account.transactions.filter(date__lte=on_date).order_by("-date", "-id").first()
    if last and last.balance is not None:
        return float(last.balance)
    return 0.0


def _compute_net_worth_series():
    """
    Build the net-worth time series broken down by account role.

    Returns:
        list[dict]: One entry per balance snapshot, oldest first, with the
        business / personal / house components and the all-up net worth.
    """

    # Cache the accounts per role so we don't re-query inside the loop.
    # Brokerage accounts are excluded because their stored balance reflects
    # only uninvested cash at the broker, not the portfolio value, and the
    # Investment category already accounts for the wallet outflows.
    house_accounts = list(Account.objects.filter(role=Account.Role.HOUSE).exclude(kind=Account.Kind.BROKERAGE))
    personal_accounts = list(Account.objects.filter(role=Account.Role.PERSONAL).exclude(kind=Account.Kind.BROKERAGE))
    business_accounts = list(Account.objects.filter(role=Account.Role.BUSINESS).exclude(kind=Account.Kind.BROKERAGE))
    # Brokerage accounts contribute via their manually-recorded portfolio
    # snapshots: for each as_of we use the latest PortfolioSnapshot on or
    # before that date, per account, summed across accounts.
    brokerage_accounts = list(Account.objects.filter(kind=Account.Kind.BROKERAGE))

    def _brokerage_value_at(on_date):
        total = 0.0
        for account in brokerage_accounts:
            snap = account.portfolio_snapshots.filter(as_of__lte=on_date).order_by("-as_of").first()
            if snap:
                total += float(snap.market_value)
        return total

    def _latest_balance_snapshot_at(on_date):
        return BalanceSnapshot.objects.filter(as_of__lte=on_date).order_by("-as_of").first()

    # Build the series over the union of every BalanceSnapshot and
    # PortfolioSnapshot date, so a broker value recorded later than the last
    # bank statement still produces a row at its own as_of.
    bank_dates = set(BalanceSnapshot.objects.values_list("as_of", flat=True))
    broker_dates = set(PortfolioSnapshot.objects.values_list("as_of", flat=True))
    timeline = sorted(bank_dates | broker_dates)

    series = []
    for as_of in timeline:
        # For dates that fall on a BalanceSnapshot we read its summary fields
        # directly; for broker-only dates we forward-fill the latest known
        # BalanceSnapshot so savings / mortgage don't drop to zero.
        bank_snap = _latest_balance_snapshot_at(as_of)
        savings = float(bank_snap.savings_total or 0) if bank_snap else 0.0
        mortgage = float(bank_snap.mortgage_balance or 0) if bank_snap else 0.0
        bank_investments = float(bank_snap.investments_total or 0) if bank_snap else 0.0

        # Investments combine any bank-side "Instrumentos financeiros" total
        # with the broker's most-recent recorded portfolio value
        investments = bank_investments + _brokerage_value_at(as_of)

        house_current = sum(_account_balance_at(a, as_of) for a in house_accounts)
        personal_current = sum(_account_balance_at(a, as_of) for a in personal_accounts)
        business_current = sum(_account_balance_at(a, as_of) for a in business_accounts)

        # House is just the household current account; the mortgage is shown
        # alongside for context but does not reduce the net-worth total
        house_total = house_current
        net_worth = business_current + personal_current + house_total + savings + investments

        series.append(
            {
                "as_of": as_of.isoformat(),
                "business": business_current,
                "personal": personal_current,
                "house": house_total,
                "house_current": house_current,
                "savings": savings,
                "investments": investments,
                "mortgage": mortgage,
                "net_worth": net_worth,
            }
        )

    return series


class NetWorthView(APIView):
    """
    Net worth over time, broken down by account role.

    - Combines the BalanceSnapshot figures with the per-account running balances
    - Returns the business / personal / household components plus the all-up total
    """

    def get(self, request):
        """
        Return the scoped net-worth series.

        Args:
            request (Request): The incoming request

        Returns:
            Response: One entry per snapshot, oldest first
        """

        return Response(_compute_net_worth_series())


class AccountsView(APIView):
    """
    Accounts with their latest known balance.

    - The latest balance is taken from the most recent transaction on the account
    - Carries scope and bank so the frontend can group accounts
    """

    def get(self, request):
        """
        Return the accounts series.

        Args:
            request (Request): The incoming request

        Returns:
            Response: One entry per account, sorted by scope and name
        """

        # Brokerage accounts (e.g. Degiro) are intentionally hidden here:
        # their balance only reflects uninvested cash at the broker, not the
        # portfolio value, which would be misleading on a banking-style list.
        accounts = []
        for account in Account.objects.exclude(kind=Account.Kind.BROKERAGE).order_by("scope", "name"):
            # Use the dated-then-id order to break ties on same-day movements
            last = account.transactions.order_by("-date", "-id").first()
            accounts.append(
                {
                    "id": account.id,
                    "name": account.name,
                    "bank": account.bank,
                    "scope": account.scope,
                    "kind": account.kind,
                    "iban": account.iban,
                    "currency": account.currency,
                    "balance": float(last.balance) if last and last.balance is not None else None,
                    "last_movement": last.date.isoformat() if last else None,
                }
            )
        return Response(accounts)


class OverviewView(APIView):
    """
    Top-level dashboard summary numbers.

    - Latest net-worth components from the most recent balance snapshot
    - Income, expenses and net for the current month and year-to-date
    - Aggregate counts so the homepage can show "X statements / Y transactions"
    """

    def get(self, request):
        """
        Return the overview snapshot.

        Args:
            request (Request): The incoming request

        Returns:
            Response: Headline figures for the homepage
        """

        # Latest snapshot, blended with business and personal account balances
        series = _compute_net_worth_series()
        net_worth_block = series[-1] if series else None

        # Date range we report on: the calendar year so far. Statements are
        # imported once a month, so a month-to-date figure would drift between
        # being "last month" and "nothing yet" depending on the import day.
        today = date.today()
        year_start = today.replace(month=1, day=1)

        def _totals(scope, since):
            """Return {"income", "expenses", "net"} for a scope and date range."""

            base = Transaction.objects.filter(date__gte=since)
            if scope:
                base = base.filter(account__scope=scope)
            income = float(base.filter(category__kind=Category.Kind.INCOME).aggregate(t=Sum("amount"))["t"] or 0)
            # Convert the stored negative amounts into a positive magnitude
            expenses = -float(base.filter(category__kind__in=EXPENSE_KINDS).aggregate(t=Sum("amount"))["t"] or 0)
            return {"income": income, "expenses": expenses, "net": income - expenses}

        def _periods(since):
            """Build the three-scope dictionary for a period start date."""

            return {
                "since": since.isoformat(),
                "all": _totals(None, since),
                "business": _totals("business", since),
                "personal": _totals("personal", since),
            }

        return Response(
            {
                "net_worth": net_worth_block,
                "year_to_date": _periods(year_start),
                "counts": {
                    # Keep the headline count consistent with the Accounts list,
                    # which hides brokerage holdings.
                    "accounts": Account.objects.exclude(kind=Account.Kind.BROKERAGE).count(),
                    "statements": StatementImport.objects.count(),
                    "transactions": Transaction.objects.count(),
                    "uncategorised": Transaction.objects.filter(category__isnull=True).count(),
                },
            }
        )


class TransactionPagination(PageNumberPagination):
    """
    Pagination for the transactions list.

    - Defaults to 50 per page
    - Allows the frontend to override with ?page_size=
    """

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500


class TransactionListView(ListAPIView):
    """
    Paginated, filterable list of transactions.

    - Filters: scope, kind (category kind), category_id, account_id, date_from, date_to, q (substring)
    - Default order is most recent first
    """

    serializer_class = TransactionSerializer
    pagination_class = TransactionPagination

    def get_queryset(self):
        """
        Build the filtered queryset from the query parameters.

        Args:
            None

        Returns:
            QuerySet[Transaction]: The matching transactions
        """

        qs = Transaction.objects.select_related("account", "category").order_by("-date", "-id")

        params = self.request.query_params
        # Restrict by account scope when given
        scope = params.get("scope")
        if scope:
            qs = qs.filter(account__scope=scope)
        # Filter by category kind (income/expense/tax/transfer/...) or by id
        kind = params.get("kind")
        if kind:
            qs = qs.filter(category__kind=kind)
        category_id = params.get("category_id")
        if category_id:
            qs = qs.filter(category_id=category_id)
        account_id = params.get("account_id")
        if account_id:
            qs = qs.filter(account_id=account_id)
        # Inclusive date bounds
        date_from = params.get("date_from")
        if date_from:
            qs = qs.filter(date__gte=date_from)
        date_to = params.get("date_to")
        if date_to:
            qs = qs.filter(date__lte=date_to)
        # Free-text search over the description
        q = params.get("q")
        if q:
            qs = qs.filter(Q(description__icontains=q))
        # An optional uncategorised-only switch
        if params.get("uncategorised") in ("1", "true", "yes"):
            qs = qs.filter(category__isnull=True)

        return qs


class TransactionDetailView(RetrieveUpdateAPIView):
    """
    Read or update a single transaction.

    - GET returns the same shape as the list view (embedded account/category)
    - PATCH accepts date, value_date, description, amount, balance, category_id
    """

    queryset = Transaction.objects.select_related("account", "category")
    serializer_class = TransactionSerializer


class CategoryListView(ListAPIView):
    """
    Flat list of categories for the edit dropdown.

    - Ordered by kind then name
    - Not paginated; the catalogue is small
    """

    queryset = Category.objects.all().order_by("kind", "name")
    serializer_class = CategoryBriefSerializer
    pagination_class = None


def _process_uploaded_file(uploaded):
    """
    Run the right importer for one uploaded file based on its extension.

    Args:
        uploaded (UploadedFile): The file from request.FILES

    Returns:
        dict: A per-file result row including the filename, the importer used
        and the counts the importer reports. On failure the dict carries an
        "error" key with a readable message instead.
    """

    name = uploaded.name
    lower = name.lower()

    # Bank-statement PDFs go through pdfplumber, so they need a real file on
    # disk; the CSV is small and decodes fine straight from memory.
    if lower.endswith(".pdf"):
        with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
            for chunk in uploaded.chunks():
                tmp.write(chunk)
            tmp.flush()
            text = extract_text(tmp.name)
        result = import_statement(text, source_file=name)
        return {
            "file": name,
            "type": "statement",
            "created": result.created,
            "skipped": result.skipped,
            "ignored": result.ignored,
            "accounts": [a.iban for a in result.accounts],
        }

    if lower.endswith(".csv"):
        text = uploaded.read().decode("utf-8")
        result = import_degiro_csv(text, source_file=name)
        return {
            "file": name,
            "type": "degiro_csv",
            "created": result["created"],
            "skipped": result["skipped"],
            "movements": result["movements"],
        }

    return {"file": name, "error": "Unsupported file type (use .pdf or .csv)"}


class UploadView(APIView):
    """
    Accept one or more bank-statement PDFs and/or Degiro CSVs.

    - Dispatches by extension: .pdf -> import_statement, .csv -> import_degiro_csv
    - Each file is processed independently so one bad file does not abort the batch
    - Returns a per-file result list with counts (or an error message)
    """

    parser_classes = [MultiPartParser]

    def post(self, request):
        """
        Process every uploaded file and report per-file results.

        Args:
            request (Request): The incoming multipart request; expects one or
                more files in the "files" field

        Returns:
            Response: {"results": [...]} with one entry per file
        """

        uploads = request.FILES.getlist("files")
        if not uploads:
            return Response({"results": [], "error": "No files in the request"}, status=400)

        results = []
        for uploaded in uploads:
            try:
                results.append(_process_uploaded_file(uploaded))
            except Exception as exc:  # noqa: BLE001 -- surface any parser/import error to the caller
                # We want a single bad file to fail loudly without taking down
                # the rest of the batch, so the exception is caught and
                # returned as part of that file's result row.
                results.append({"file": uploaded.name, "error": str(exc)})
        return Response({"results": results})


class PortfolioSnapshotView(APIView):
    """
    Record (or update) a manual portfolio-value snapshot.

    - POST upserts on (account, as_of) so re-submitting the same date just
      corrects the value, matching the record_portfolio_value CLI command
    - Account must be brokerage-kind; the serializer enforces that
    """

    def post(self, request):
        """
        Validate the payload and upsert the snapshot.

        Args:
            request (Request): The incoming JSON request with account_id,
                as_of, market_value and optional note

        Returns:
            Response: The serialized snapshot, 201 on create, 200 on update
        """

        serializer = PortfolioSnapshotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        snapshot, created = PortfolioSnapshot.objects.update_or_create(
            account=data["account"],
            as_of=data["as_of"],
            defaults={"market_value": data["market_value"], "note": data.get("note", "")},
        )
        # Re-serialize the saved row so the response carries the nested
        # account brief and the created_at timestamp
        return Response(PortfolioSnapshotSerializer(snapshot).data, status=201 if created else 200)


class ResetView(APIView):
    """
    Wipe every imported record so the user can re-upload from scratch.

    - Deletes transactions, accounts, statements and both kinds of snapshot
    - Keeps configuration (categories, rules, ignore patterns) so the next
      upload auto-classifies as before
    - Requires {"confirm": "RESET"} in the body to defend against an
      accidental click; anything else returns a 400
    """

    def post(self, request):
        """
        Validate the confirmation token and delete the data tables.

        Args:
            request (Request): The incoming JSON request; must carry
                {"confirm": "RESET"}

        Returns:
            Response: A dict with the deleted-row counts per model, plus a
            kept block that documents what was preserved
        """

        if (request.data or {}).get("confirm") != "RESET":
            return Response(
                {"error": 'Send {"confirm": "RESET"} to wipe the data.'},
                status=400,
            )

        # Delete order respects the foreign-key graph: transactions and
        # portfolio snapshots point at accounts; balance snapshots point at
        # statements; nothing else points at accounts once those are gone.
        deleted = {
            "transactions": Transaction.objects.all().delete()[0],
            "portfolio_snapshots": PortfolioSnapshot.objects.all().delete()[0],
            "balance_snapshots": BalanceSnapshot.objects.all().delete()[0],
            "statements": StatementImport.objects.all().delete()[0],
            "accounts": Account.objects.all().delete()[0],
        }
        # Configuration is preserved so the next upload classifies cleanly
        kept = {
            "categories": Category.objects.count(),
            "category_rules": CategoryRule.objects.count(),
            "ignore_rules": IgnoreRule.objects.count(),
        }
        return Response({"deleted": deleted, "kept": kept})
