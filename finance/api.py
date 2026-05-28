# Author: xhico
# Date: May 27, 2026
"""
Read-only dashboard endpoints for the finance app.

These aggregate the imported data for the dashboards: income, expenses,
cashflow, accounts, balance snapshots and a filterable transactions list.
"""

from datetime import date

from django.db.models import Q, Sum
from django.db.models.functions import TruncMonth
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from finance.models import Account, BalanceSnapshot, Category, StatementImport, Transaction
from finance.serializers import TransactionSerializer


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


class IncomeView(APIView):
    """
    Monthly and quarterly income over time.

    - Sums transactions in income-kind categories by month
    - Rolls the months up into calendar quarters
    """

    def get(self, request):
        """
        Return the income series.

        Args:
            request (Request): The incoming request

        Returns:
            Response: Monthly and quarterly income totals
        """

        rows = (
            Transaction.objects.filter(category__kind=Category.Kind.INCOME)
            .annotate(month=TruncMonth("date"))
            .values("month")
            .annotate(total=Sum("amount"))
            .order_by("month")
        )

        monthly = [{"period": _month_key(r["month"]), "income": float(r["total"])} for r in rows]

        # Roll the monthly totals up into calendar quarters
        quarters = {}
        for r in rows:
            q = _quarter(r["month"])
            quarters[q] = quarters.get(q, 0.0) + float(r["total"])
        quarterly = [{"period": q, "income": total} for q, total in sorted(quarters.items())]

        return Response({"monthly": monthly, "quarterly": quarterly})


class ExpensesView(APIView):
    """
    Expense aggregates: monthly totals, per-category totals and per-month-per-category.

    - "Expense" here means any expense or tax category, by sign-agnostic sum
    - Amounts are returned as positive numbers so charts plot upwards
    """

    def get(self, request):
        """
        Return the expense aggregates.

        Args:
            request (Request): The incoming request

        Returns:
            Response: Three series: monthly totals, by_category, monthly_by_category
        """

        base = Transaction.objects.filter(category__kind__in=EXPENSE_KINDS)

        # Monthly totals (positive numbers, even though amounts are stored negative)
        monthly_rows = (
            base.annotate(month=TruncMonth("date")).values("month").annotate(total=Sum("amount")).order_by("month")
        )
        monthly = [{"period": _month_key(r["month"]), "total": -float(r["total"])} for r in monthly_rows]

        # Per-category totals across the whole period
        by_cat_rows = base.values("category__name", "category__kind").annotate(total=Sum("amount")).order_by("total")
        by_category = [
            {"category": r["category__name"], "kind": r["category__kind"], "total": -float(r["total"])}
            for r in by_cat_rows
        ]

        # Per-month-per-category (for stacked charts)
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

        return Response({"monthly": monthly, "by_category": by_category, "monthly_by_category": monthly_by_category})


class CashflowView(APIView):
    """
    Monthly net cashflow (income minus expenses).

    - Income, expenses and net per month
    - Internal transfers and investments are excluded from in/out totals
    """

    def get(self, request):
        """
        Return the cashflow series.

        Args:
            request (Request): The incoming request

        Returns:
            Response: One entry per month with income, expenses and net
        """

        # Income credits per month
        inc_rows = (
            Transaction.objects.filter(category__kind=Category.Kind.INCOME)
            .annotate(month=TruncMonth("date"))
            .values("month")
            .annotate(total=Sum("amount"))
        )
        # Expense and tax debits per month
        exp_rows = (
            Transaction.objects.filter(category__kind__in=EXPENSE_KINDS)
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

        return Response(series)


class NetWorthView(APIView):
    """
    Savings and net worth over time from the balance snapshots.

    - Reports the headline balances captured each month
    - Computes net worth as assets minus the mortgage balance
    """

    def get(self, request):
        """
        Return the net-worth series.

        Args:
            request (Request): The incoming request

        Returns:
            Response: One entry per snapshot, oldest first
        """

        series = []
        for snap in BalanceSnapshot.objects.order_by("as_of"):
            current = float(snap.current_total or 0)
            savings = float(snap.savings_total or 0)
            investments = float(snap.investments_total or 0)
            mortgage = float(snap.mortgage_balance or 0)
            series.append(
                {
                    "as_of": snap.as_of.isoformat(),
                    "current": current,
                    "savings": savings,
                    "investments": investments,
                    "mortgage": mortgage,
                    "net_worth": current + savings + investments - mortgage,
                }
            )

        return Response(series)


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

        accounts = []
        for account in Account.objects.order_by("scope", "name"):
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

        # Latest balance snapshot, if any imports have produced one
        snap = BalanceSnapshot.objects.order_by("-as_of").first()
        net_worth_block = None
        if snap:
            current = float(snap.current_total or 0)
            savings = float(snap.savings_total or 0)
            investments = float(snap.investments_total or 0)
            mortgage = float(snap.mortgage_balance or 0)
            net_worth_block = {
                "as_of": snap.as_of.isoformat(),
                "current": current,
                "savings": savings,
                "investments": investments,
                "mortgage": mortgage,
                "net_worth": current + savings + investments - mortgage,
            }

        # Date range we report on: current month and current calendar year
        today = date.today()
        month_start = today.replace(day=1)
        year_start = today.replace(month=1, day=1)

        def _sum(qs, since):
            """Return the sum of amounts in a queryset from a start date."""

            # An empty result means zero, not None
            return float(qs.filter(date__gte=since).aggregate(t=Sum("amount"))["t"] or 0)

        income_qs = Transaction.objects.filter(category__kind=Category.Kind.INCOME)
        expense_qs = Transaction.objects.filter(category__kind__in=EXPENSE_KINDS)

        mtd_income = _sum(income_qs, month_start)
        mtd_expenses = -_sum(expense_qs, month_start)
        ytd_income = _sum(income_qs, year_start)
        ytd_expenses = -_sum(expense_qs, year_start)

        return Response(
            {
                "net_worth": net_worth_block,
                "month_to_date": {
                    "since": month_start.isoformat(),
                    "income": mtd_income,
                    "expenses": mtd_expenses,
                    "net": mtd_income - mtd_expenses,
                },
                "year_to_date": {
                    "since": year_start.isoformat(),
                    "income": ytd_income,
                    "expenses": ytd_expenses,
                    "net": ytd_income - ytd_expenses,
                },
                "counts": {
                    "accounts": Account.objects.count(),
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
