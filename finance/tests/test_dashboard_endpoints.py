# Author: xhico
# Date: May 27, 2026
"""Tests for the expanded dashboard API: expenses, cashflow, overview, accounts, transactions."""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from rest_framework.test import APIClient

from finance.models import (
    Account,
    BalanceSnapshot,
    Category,
    CategoryRule,
    PortfolioSnapshot,
    StatementImport,
    Transaction,
)
from finance.services import classify_transactions


@pytest.fixture
def api_client():
    """
    Provide an authenticated DRF client.

    Args:
        None

    Returns:
        APIClient: A client logged in as a test user
    """

    user = User.objects.create_user(username="tester", password="pw")
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def seeded():
    """
    Build a small fixture set: two accounts and a handful of classified movements.

    Args:
        None

    Returns:
        dict: References to the created records by short name
    """

    # Personal current account with an income credit and an expense debit; this
    # one acts as the household account that holds the mortgage in the snapshot
    house = Account.objects.create(
        name="House", bank="Bank", iban="PT50000000000000000000010", scope="personal", role=Account.Role.HOUSE
    )
    # Business current account with a tax payment
    biz = Account.objects.create(
        name="Business", bank="Bank", iban="PT50000000000000000000011", scope="business", role=Account.Role.BUSINESS
    )

    salary = Category.objects.create(name="Salary", kind=Category.Kind.INCOME)
    groceries = Category.objects.create(name="Groceries", kind=Category.Kind.EXPENSE)
    tax = Category.objects.create(name="Tax", kind=Category.Kind.TAX)
    CategoryRule.objects.create(match_text="ACME PAYROLL", sign=CategoryRule.Sign.CREDIT, category=salary, priority=10)
    CategoryRule.objects.create(match_text="MARKET", sign=CategoryRule.Sign.DEBIT, category=groceries, priority=50)
    CategoryRule.objects.create(match_text="VAT PAY", sign=CategoryRule.Sign.DEBIT, category=tax, priority=50)

    Transaction.objects.create(
        account=house,
        date=date(2026, 4, 15),
        description="ACME PAYROLL APR",
        amount=Decimal("1500.00"),
        balance=Decimal("1500.00"),
    )
    Transaction.objects.create(
        account=house,
        date=date(2026, 4, 20),
        description="MARKET DAILY",
        amount=Decimal("-100.00"),
        balance=Decimal("1400.00"),
    )
    Transaction.objects.create(
        account=biz,
        date=date(2026, 4, 22),
        description="VAT PAY APR",
        amount=Decimal("-200.00"),
        balance=Decimal("800.00"),
    )
    Transaction.objects.create(
        account=house,
        date=date(2026, 3, 15),
        description="ACME PAYROLL MAR",
        amount=Decimal("1500.00"),
        balance=Decimal("1500.00"),
    )
    classify_transactions()

    statement = StatementImport.objects.create(bank="cgd", scope="personal", period_end=date(2026, 4, 30))
    BalanceSnapshot.objects.create(
        statement=statement,
        as_of=date(2026, 4, 30),
        current_total=Decimal("1000.00"),
        savings_total=Decimal("5000.00"),
        investments_total=Decimal("0.00"),
        mortgage_balance=Decimal("100000.00"),
    )

    return {"house": house, "biz": biz, "salary": salary, "groceries": groceries, "tax": tax}


@pytest.mark.django_db
def test_expenses_endpoint_returns_monthly_and_category(api_client, seeded):
    """
    Expenses endpoint reports monthly totals and per-category aggregates.

    Args:
        api_client (APIClient): Authenticated client
        seeded (dict): Fixture data

    Returns:
        None
    """

    response = api_client.get("/api/dashboard/expenses/")

    assert response.status_code == 200
    body = response.data
    assert set(body) == {"all", "business", "personal"}
    # April had 100 in Groceries and 200 in Tax = 300 of money out
    assert {"period": "2026-04", "total": 300.0} in body["all"]["monthly"]
    categories = {row["category"]: row["total"] for row in body["all"]["by_category"]}
    assert categories["Groceries"] == 100.0
    assert categories["Tax"] == 200.0
    assert {"period": "2026-04", "category": "Groceries", "total": 100.0} in body["all"]["monthly_by_category"]
    # Scoped views split the buckets by account scope
    biz_cats = {row["category"]: row["total"] for row in body["business"]["by_category"]}
    personal_cats = {row["category"]: row["total"] for row in body["personal"]["by_category"]}
    assert biz_cats == {"Tax": 200.0}
    assert personal_cats == {"Groceries": 100.0}


@pytest.mark.django_db
def test_cashflow_endpoint_nets_income_and_expense(api_client, seeded):
    """
    Cashflow endpoint pairs the monthly income and expense streams.

    Args:
        api_client (APIClient): Authenticated client
        seeded (dict): Fixture data

    Returns:
        None
    """

    response = api_client.get("/api/dashboard/cashflow/")

    assert response.status_code == 200
    body = response.data
    # The response now ships three scoped series side by side
    assert set(body) == {"all", "business", "personal"}

    all_months = {row["period"]: row for row in body["all"]}
    # April: income 1500 (personal salary), expenses 300 (100 groceries + 200 tax),
    # net 1200 across the combined view
    assert all_months["2026-04"]["income"] == 1500.0
    assert all_months["2026-04"]["expenses"] == 300.0
    assert all_months["2026-04"]["net"] == 1200.0
    # March: income 1500, no expenses
    assert all_months["2026-03"]["income"] == 1500.0
    assert all_months["2026-03"]["expenses"] == 0.0

    # Scoped views: business only has the VAT tax debit, personal only the salary + groceries
    biz_apr = next(r for r in body["business"] if r["period"] == "2026-04")
    assert biz_apr["income"] == 0.0
    assert biz_apr["expenses"] == 200.0
    personal_apr = next(r for r in body["personal"] if r["period"] == "2026-04")
    assert personal_apr["income"] == 1500.0
    assert personal_apr["expenses"] == 100.0


@pytest.mark.django_db
def test_accounts_endpoint_reports_latest_balance(api_client, seeded):
    """
    Accounts endpoint returns each account with its latest balance.

    Args:
        api_client (APIClient): Authenticated client
        seeded (dict): Fixture data

    Returns:
        None
    """

    response = api_client.get("/api/dashboard/accounts/")

    assert response.status_code == 200
    by_name = {a["name"]: a for a in response.data}
    # House account latest balance is from the April 20 expense, which leaves 1400
    assert by_name["House"]["balance"] == 1400.0
    assert by_name["House"]["scope"] == "personal"
    assert by_name["Business"]["balance"] == 800.0


@pytest.mark.django_db
def test_brokerage_accounts_hidden_from_dashboards(api_client, seeded):
    """
    Brokerage accounts are excluded from the Accounts list, the overview
    count and the role-based net-worth buckets.

    Args:
        api_client (APIClient): Authenticated client
        seeded (dict): Fixture data

    Returns:
        None
    """

    # Add a brokerage account with a cash balance that, if included, would
    # distort the personal net-worth bucket and inflate the account count.
    broker = Account.objects.create(
        name="Broker",
        bank="Broker",
        iban="BROKERIBAN",
        scope="personal",
        role=Account.Role.PERSONAL,
        kind=Account.Kind.BROKERAGE,
    )
    broker_cash = Decimal("123.45")
    Transaction.objects.create(
        account=broker,
        date=date(2026, 4, 30),
        description="flatex Deposit",
        amount=Decimal("-100.00"),
        balance=broker_cash,
    )

    accounts = api_client.get("/api/dashboard/accounts/").data
    assert "Broker" not in {a["name"] for a in accounts}
    # The two banking accounts from the seeded fixture are still there
    assert {a["name"] for a in accounts} == {"House", "Business"}

    overview = api_client.get("/api/dashboard/overview/").data
    assert overview["counts"]["accounts"] == 2

    net_worth = api_client.get("/api/dashboard/net-worth/").data
    # The broker cash must not leak into the personal bucket
    for entry in net_worth:
        assert entry["personal"] != float(broker_cash)


@pytest.mark.django_db
def test_overview_endpoint_summary_numbers(api_client, seeded):
    """
    Overview endpoint reports counts and the latest snapshot.

    Args:
        api_client (APIClient): Authenticated client
        seeded (dict): Fixture data

    Returns:
        None
    """

    response = api_client.get("/api/dashboard/overview/")

    assert response.status_code == 200
    body = response.data
    assert body["counts"]["accounts"] == 2
    assert body["counts"]["transactions"] == 4
    nw = body["net_worth"]
    # House is just the household account's last balance; mortgage is reported
    # alongside but no longer reduces net worth. Net = business + house +
    # personal + savings + investments.
    assert nw["business"] == 800.0
    assert nw["house"] == 1400.0
    assert nw["personal"] == 0.0
    assert nw["savings"] == 5000.0
    assert nw["net_worth"] == 800.0 + 1400.0 + 0.0 + 5000.0


@pytest.mark.django_db
def test_transactions_list_filters_and_paginates(api_client, seeded):
    """
    Transactions list supports scope, kind and search filters with pagination.

    Args:
        api_client (APIClient): Authenticated client
        seeded (dict): Fixture data

    Returns:
        None
    """

    # Scope filter: only personal account movements
    response = api_client.get("/api/transactions/?scope=personal")
    assert response.status_code == 200
    assert response.data["count"] == 3

    # Kind filter: only expenses
    response = api_client.get("/api/transactions/?kind=expense")
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["category"]["name"] == "Groceries"

    # Search filter
    response = api_client.get("/api/transactions/?q=payroll")
    assert response.status_code == 200
    assert response.data["count"] == 2


@pytest.mark.django_db
def test_investments_endpoint_includes_valuation_block(api_client):
    """
    The investments endpoint exposes the latest portfolio snapshot alongside
    the cumulative cost basis, so the dashboard can show current value and
    unrealised gain.

    Args:
        api_client (APIClient): Authenticated client

    Returns:
        None
    """

    broker = Account.objects.create(
        name="Broker",
        bank="Broker",
        iban="BROKERIBAN",
        scope="personal",
        role=Account.Role.PERSONAL,
        kind=Account.Kind.BROKERAGE,
    )
    investment = Category.objects.create(name="Investment", kind=Category.Kind.INVESTMENT)
    # Two deposits adding to a cost basis of 200
    Transaction.objects.create(
        account=broker,
        date=date(2026, 1, 15),
        description="flatex Deposit",
        amount=Decimal("-120.00"),
        category=investment,
    )
    Transaction.objects.create(
        account=broker,
        date=date(2026, 2, 15),
        description="flatex Deposit",
        amount=Decimal("-80.00"),
        category=investment,
    )
    # Recorded snapshot above the cost basis -> positive unrealised gain
    PortfolioSnapshot.objects.create(account=broker, as_of=date(2026, 2, 28), market_value=Decimal("230.00"))

    response = api_client.get("/api/dashboard/investments/")

    assert response.status_code == 200
    all_block = response.data["all"]
    assert all_block["net_invested"] == 200.0
    valuation = all_block["valuation"]
    assert valuation["current_value"] == 230.0
    assert valuation["as_of"] == "2026-02-28"
    assert valuation["unrealised"] == 30.0
    assert valuation["history"] == [{"as_of": "2026-02-28", "market_value": 230.0}]


@pytest.mark.django_db
def test_investments_endpoint_returns_empty_valuation_without_snapshot(api_client):
    """
    With no portfolio snapshots recorded, the valuation block reports nulls
    so the dashboard can fall back to a "no data" state.

    Args:
        api_client (APIClient): Authenticated client

    Returns:
        None
    """

    response = api_client.get("/api/dashboard/investments/")

    assert response.status_code == 200
    valuation = response.data["all"]["valuation"]
    assert valuation == {"current_value": None, "as_of": None, "unrealised": None, "history": []}


@pytest.mark.django_db
def test_record_portfolio_value_command_upserts():
    """
    The CLI creates a snapshot the first time and updates it on re-run.

    Args:
        None

    Returns:
        None
    """

    broker = Account.objects.create(
        name="Broker",
        bank="Broker",
        iban="BROKERIBAN",
        scope="personal",
        role=Account.Role.PERSONAL,
        kind=Account.Kind.BROKERAGE,
    )

    call_command("record_portfolio_value", broker.iban, "2026-02-28", "150.00")
    assert PortfolioSnapshot.objects.filter(account=broker, as_of=date(2026, 2, 28)).count() == 1
    assert PortfolioSnapshot.objects.get(account=broker, as_of=date(2026, 2, 28)).market_value == Decimal("150.00")

    # Re-running with a different value updates in place
    call_command("record_portfolio_value", broker.iban, "2026-02-28", "175.00", "--note", "corrected")
    assert PortfolioSnapshot.objects.filter(account=broker, as_of=date(2026, 2, 28)).count() == 1
    snap = PortfolioSnapshot.objects.get(account=broker, as_of=date(2026, 2, 28))
    assert snap.market_value == Decimal("175.00")
    assert snap.note == "corrected"


@pytest.mark.django_db
def test_categories_endpoint_lists_known_categories(api_client, seeded):
    """
    The categories endpoint returns a flat list with id, name and kind.

    Args:
        api_client (APIClient): Authenticated client
        seeded (dict): Fixture data

    Returns:
        None
    """

    response = api_client.get("/api/categories/")

    assert response.status_code == 200
    names = {row["name"] for row in response.data}
    assert {"Salary", "Groceries", "Tax"} <= names
    # Every row carries the three brief fields the edit dropdown needs
    assert all(set(row) == {"id", "name", "kind"} for row in response.data)


@pytest.mark.django_db
def test_transaction_patch_updates_category_and_description(api_client, seeded):
    """
    PATCH /api/transactions/<id>/ updates the category, description and amount.

    Args:
        api_client (APIClient): Authenticated client
        seeded (dict): Fixture data

    Returns:
        None
    """

    txn = Transaction.objects.filter(description="ACME PAYROLL APR").first()
    new_cat = Category.objects.create(name="Other income", kind=Category.Kind.INCOME)

    response = api_client.patch(
        f"/api/transactions/{txn.id}/",
        data={"category_id": new_cat.id, "description": "Adjusted description", "amount": "1234.56"},
        format="json",
    )

    assert response.status_code == 200
    txn.refresh_from_db()
    assert txn.category_id == new_cat.id
    assert txn.description == "Adjusted description"
    assert txn.amount == Decimal("1234.56")
    # The response embeds the category brief so the frontend can rerender
    assert response.data["category"]["id"] == new_cat.id


@pytest.mark.django_db
def test_transaction_patch_can_clear_category(api_client, seeded):
    """
    Passing category_id=null detaches the category from the transaction.

    Args:
        api_client (APIClient): Authenticated client
        seeded (dict): Fixture data

    Returns:
        None
    """

    txn = Transaction.objects.filter(description="ACME PAYROLL APR").first()
    assert txn.category is not None

    response = api_client.patch(
        f"/api/transactions/{txn.id}/",
        data={"category_id": None},
        format="json",
    )

    assert response.status_code == 200
    txn.refresh_from_db()
    assert txn.category is None


@pytest.mark.django_db
def test_investments_endpoint_exposes_brokerage_accounts(api_client):
    """
    The investments endpoint includes the brokerage account list so the
    frontend can populate the set-value modal's picker.

    Args:
        api_client (APIClient): Authenticated client

    Returns:
        None
    """

    Account.objects.create(
        name="Broker",
        bank="Broker",
        iban="BROKERIBAN",
        scope="personal",
        role=Account.Role.PERSONAL,
        kind=Account.Kind.BROKERAGE,
    )

    response = api_client.get("/api/dashboard/investments/")

    assert response.status_code == 200
    brokerages = response.data["brokerage_accounts"]
    assert len(brokerages) == 1
    assert brokerages[0]["name"] == "Broker"
    assert brokerages[0]["iban"] == "BROKERIBAN"


@pytest.mark.django_db
def test_portfolio_snapshot_post_creates_and_upserts(api_client):
    """
    POST /api/portfolio-snapshots/ creates a snapshot first, then updates it
    when the same (account, as_of) pair is submitted again.

    Args:
        api_client (APIClient): Authenticated client

    Returns:
        None
    """

    broker = Account.objects.create(
        name="Broker",
        bank="Broker",
        iban="BROKERIBAN",
        scope="personal",
        role=Account.Role.PERSONAL,
        kind=Account.Kind.BROKERAGE,
    )

    first = api_client.post(
        "/api/portfolio-snapshots/",
        data={"account_id": broker.id, "as_of": "2026-02-28", "market_value": "10.00"},
        format="json",
    )
    assert first.status_code == 201
    assert PortfolioSnapshot.objects.filter(account=broker).count() == 1

    second = api_client.post(
        "/api/portfolio-snapshots/",
        data={"account_id": broker.id, "as_of": "2026-02-28", "market_value": "25.00", "note": "corrected"},
        format="json",
    )
    assert second.status_code == 200
    assert PortfolioSnapshot.objects.filter(account=broker).count() == 1
    snap = PortfolioSnapshot.objects.get(account=broker, as_of=date(2026, 2, 28))
    assert snap.market_value == Decimal("25.00")
    assert snap.note == "corrected"
    # The response embeds the account brief for the frontend
    assert second.data["account"]["iban"] == "BROKERIBAN"


@pytest.mark.django_db
def test_portfolio_snapshot_post_rejects_non_brokerage_account(api_client, seeded):
    """
    The endpoint refuses to attach a snapshot to a non-brokerage account.

    Args:
        api_client (APIClient): Authenticated client
        seeded (dict): Fixture data; the House account is kind=current

    Returns:
        None
    """

    response = api_client.post(
        "/api/portfolio-snapshots/",
        data={"account_id": seeded["house"].id, "as_of": "2026-02-28", "market_value": "10.00"},
        format="json",
    )

    assert response.status_code == 400
    assert "account_id" in response.data


@pytest.mark.django_db
def test_upload_endpoint_dispatches_pdf_and_csv(api_client):
    """
    POSTing a CGD-format text file (.pdf extension) and a Degiro CSV runs
    each through its parser and returns a per-file result row.

    Args:
        api_client (APIClient): Authenticated client

    Returns:
        None
    """

    from io import BytesIO
    from pathlib import Path

    from django.core.files.uploadedfile import SimpleUploadedFile

    fixtures = Path(__file__).parent / "fixtures"
    csv_bytes = (fixtures / "degiro_account_sample.csv").read_bytes()

    response = api_client.post(
        "/api/upload/",
        data={
            "files": [
                SimpleUploadedFile("degiro.csv", csv_bytes, content_type="text/csv"),
                SimpleUploadedFile("noise.txt", BytesIO(b"junk").read(), content_type="text/plain"),
            ],
        },
        format="multipart",
    )

    assert response.status_code == 200
    results = {r["file"]: r for r in response.data["results"]}
    # The CSV was parsed by the Degiro importer
    assert results["degiro.csv"]["type"] == "degiro_csv"
    assert results["degiro.csv"]["created"] >= 1
    # The unsupported extension is reported as an error rather than aborting
    assert "error" in results["noise.txt"]


@pytest.mark.django_db
def test_upload_endpoint_rejects_empty_request(api_client):
    """
    POSTing with no files returns a 400 with a readable error message.

    Args:
        api_client (APIClient): Authenticated client

    Returns:
        None
    """

    response = api_client.post("/api/upload/", data={}, format="multipart")
    assert response.status_code == 400
    assert "No files" in response.data.get("error", "")


@pytest.mark.django_db
def test_seed_get_returns_current_state(api_client, seeded):
    """
    GET /api/seed/ returns the live categories, rules and ignore patterns
    in the same shape as seed_rules.json.

    Args:
        api_client (APIClient): Authenticated client
        seeded (dict): Fixture data; creates categories and rules

    Returns:
        None
    """

    response = api_client.get("/api/seed/")

    assert response.status_code == 200
    body = response.data
    assert set(body) == {"categories", "rules", "ignore"}
    cat_names = {c["name"] for c in body["categories"]}
    assert {"Salary", "Groceries", "Tax"} <= cat_names
    rule_matches = {r["match_text"] for r in body["rules"]}
    assert {"ACME PAYROLL", "MARKET", "VAT PAY"} <= rule_matches


@pytest.mark.django_db
def test_seed_post_applies_payload_via_file_upload(api_client):
    """
    POST /api/seed/ with a JSON file applies categories, rules and ignore
    patterns and reports upsert counts.

    Args:
        api_client (APIClient): Authenticated client

    Returns:
        None
    """

    import json as json_module

    from django.core.files.uploadedfile import SimpleUploadedFile

    payload = {
        "categories": [
            {"name": "Salary", "kind": "income"},
            {"name": "Online shopping", "kind": "expense"},
        ],
        "rules": [
            {"match_text": "EXAMPLE", "sign": "any", "category": "Salary", "priority": 10},
        ],
        "ignore": [
            {"match_text": "NOISE", "note": "test"},
        ],
    }
    upload = SimpleUploadedFile(
        "seed_rules.json", json_module.dumps(payload).encode("utf-8"), content_type="application/json"
    )

    response = api_client.post("/api/seed/", data={"file": upload}, format="multipart")

    assert response.status_code == 200
    assert response.data["rules_created"] == 1
    assert response.data["ignore_created"] == 1
    # Re-applying the same payload upserts in place
    upload2 = SimpleUploadedFile(
        "seed_rules.json", json_module.dumps(payload).encode("utf-8"), content_type="application/json"
    )
    response = api_client.post("/api/seed/", data={"file": upload2}, format="multipart")
    assert response.status_code == 200
    assert response.data["rules_created"] == 0
    assert response.data["rules_updated"] == 1


@pytest.mark.django_db
def test_seed_post_accepts_json_body(api_client):
    """
    POST /api/seed/ also accepts a raw JSON body so the endpoint is usable
    without a file upload.

    Args:
        api_client (APIClient): Authenticated client

    Returns:
        None
    """

    response = api_client.post(
        "/api/seed/",
        data={
            "categories": [{"name": "Other income", "kind": "income"}],
            "rules": [],
            "ignore": [],
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["categories"] >= 1


@pytest.mark.django_db
def test_seed_post_rejects_bad_json(api_client):
    """
    A malformed JSON file returns 400 with a readable error.

    Args:
        api_client (APIClient): Authenticated client

    Returns:
        None
    """

    from django.core.files.uploadedfile import SimpleUploadedFile

    upload = SimpleUploadedFile("bad.json", b"{ not valid json", content_type="application/json")
    response = api_client.post("/api/seed/", data={"file": upload}, format="multipart")
    assert response.status_code == 400
    assert "Invalid JSON" in response.data["error"]


@pytest.mark.django_db
def test_seed_post_rejects_rule_with_unknown_category(api_client):
    """
    A rule referencing an unseeded category returns 400 rather than crashing.

    Args:
        api_client (APIClient): Authenticated client

    Returns:
        None
    """

    response = api_client.post(
        "/api/seed/",
        data={
            "categories": [],
            "rules": [{"match_text": "X", "category": "MissingCategory", "priority": 10}],
        },
        format="json",
    )

    assert response.status_code == 400
    assert "MissingCategory" in response.data["error"] or "Unknown category" in response.data["error"]


@pytest.mark.django_db
def test_categorise_bulk_applies_to_explicit_ids(api_client):
    """
    POST /api/transactions/categorise-bulk/ updates every transaction whose
    id is in the request payload, regardless of current category.

    Args:
        api_client (APIClient): Authenticated client

    Returns:
        None
    """

    account = Account.objects.create(name="House", bank="Bank", iban="PT50000000000000000000040", scope="personal")
    shopping = Category.objects.create(name="Online shopping", kind=Category.Kind.EXPENSE)
    existing = Category.objects.create(name="Other", kind=Category.Kind.EXPENSE)

    a = Transaction.objects.create(
        account=account, date=date(2026, 5, 1), description="ROW A", amount=Decimal("-10.00")
    )
    b = Transaction.objects.create(
        account=account, date=date(2026, 5, 2), description="ROW B", amount=Decimal("-20.00"), category=existing
    )
    # Not in the selection: must NOT be touched
    c = Transaction.objects.create(account=account, date=date(2026, 5, 3), description="ROW C", amount=Decimal("-5.00"))

    response = api_client.post(
        "/api/transactions/categorise-bulk/",
        data={"ids": [a.id, b.id], "category_id": shopping.id},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["updated"] == 2
    a.refresh_from_db()
    b.refresh_from_db()
    c.refresh_from_db()
    assert a.category_id == shopping.id
    assert b.category_id == shopping.id  # was Other, now overwritten
    assert c.category is None


@pytest.mark.django_db
def test_categorise_bulk_can_clear_with_null_category(api_client):
    """
    Passing category_id=null detaches the category from every selected row.

    Args:
        api_client (APIClient): Authenticated client

    Returns:
        None
    """

    account = Account.objects.create(name="House", bank="Bank", iban="PT50000000000000000000041", scope="personal")
    cat = Category.objects.create(name="Misc", kind=Category.Kind.EXPENSE)
    t = Transaction.objects.create(
        account=account, date=date(2026, 5, 1), description="X", amount=Decimal("-1.00"), category=cat
    )

    response = api_client.post(
        "/api/transactions/categorise-bulk/",
        data={"ids": [t.id], "category_id": None},
        format="json",
    )

    assert response.status_code == 200
    t.refresh_from_db()
    assert t.category is None


@pytest.mark.django_db
def test_categorise_bulk_validates_inputs(api_client, seeded):
    """
    Empty ids returns 400; non-integer ids return 400; unknown category_id
    returns 400.

    Args:
        api_client (APIClient): Authenticated client
        seeded (dict): Fixture data, just to have some categories around

    Returns:
        None
    """

    # Empty / missing ids
    r = api_client.post("/api/transactions/categorise-bulk/", data={"ids": [], "category_id": None}, format="json")
    assert r.status_code == 400

    # Non-integer ids
    r = api_client.post(
        "/api/transactions/categorise-bulk/",
        data={"ids": ["abc"], "category_id": None},
        format="json",
    )
    assert r.status_code == 400

    # Unknown category_id
    r = api_client.post(
        "/api/transactions/categorise-bulk/",
        data={"ids": [1], "category_id": 99999},
        format="json",
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_categorise_matching_applies_to_every_uncategorised_match(api_client):
    """
    POST /api/transactions/categorise-matching/ categorises every uncategorised
    transaction whose description contains the match text, leaving already
    classified rows untouched.

    Args:
        api_client (APIClient): Authenticated client

    Returns:
        None
    """

    account = Account.objects.create(name="House", bank="Bank", iban="PT50000000000000000000030", scope="personal")
    shopping = Category.objects.create(name="Online shopping", kind=Category.Kind.EXPENSE)
    existing = Category.objects.create(name="Other", kind=Category.Kind.EXPENSE)

    a = Transaction.objects.create(
        account=account, date=date(2026, 5, 1), description="COMPRA VENDORX 1", amount=Decimal("-10.00")
    )
    b = Transaction.objects.create(
        account=account, date=date(2026, 5, 2), description="COMPRA vendorx 2", amount=Decimal("-12.00")
    )
    # Already categorised: must NOT be touched when only_uncategorised is true
    c = Transaction.objects.create(
        account=account,
        date=date(2026, 5, 3),
        description="COMPRA VENDORX 3",
        amount=Decimal("-8.00"),
        category=existing,
    )
    # Different description: must NOT match
    d = Transaction.objects.create(
        account=account, date=date(2026, 5, 4), description="COMPRA OTHER", amount=Decimal("-5.00")
    )

    response = api_client.post(
        "/api/transactions/categorise-matching/",
        data={"match_text": "vendorx", "category_id": shopping.id},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["updated"] == 2
    a.refresh_from_db()
    b.refresh_from_db()
    c.refresh_from_db()
    d.refresh_from_db()
    assert a.category_id == shopping.id
    assert b.category_id == shopping.id
    # Already categorised row stays as-is
    assert c.category_id == existing.id
    # Non-matching row stays uncategorised
    assert d.category is None


@pytest.mark.django_db
def test_categorise_matching_validates_inputs(api_client):
    """
    Empty match_text returns 400; unknown category_id returns 400.

    Args:
        api_client (APIClient): Authenticated client

    Returns:
        None
    """

    response = api_client.post(
        "/api/transactions/categorise-matching/",
        data={"match_text": "", "category_id": None},
        format="json",
    )
    assert response.status_code == 400

    response = api_client.post(
        "/api/transactions/categorise-matching/",
        data={"match_text": "vendor", "category_id": 99999},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_reset_endpoint_wipes_data_and_keeps_configuration(api_client, seeded):
    """
    POST /api/reset/ with the confirm token deletes every imported record
    but keeps categories, rules and ignore patterns intact.

    Args:
        api_client (APIClient): Authenticated client
        seeded (dict): Fixture data; primes accounts, transactions and rules

    Returns:
        None
    """

    PortfolioSnapshot.objects.create(
        account=Account.objects.create(
            name="Broker",
            bank="Broker",
            iban="BROKERIBAN",
            scope="personal",
            role=Account.Role.PERSONAL,
            kind=Account.Kind.BROKERAGE,
        ),
        as_of=date(2026, 4, 30),
        market_value=Decimal("50.00"),
    )
    accounts_before = Account.objects.count()
    transactions_before = Transaction.objects.count()
    rules_before = CategoryRule.objects.count()

    response = api_client.post("/api/reset/", data={"confirm": "RESET"}, format="json")

    assert response.status_code == 200
    deleted = response.data["deleted"]
    assert deleted["accounts"] == accounts_before
    assert deleted["transactions"] == transactions_before
    assert deleted["portfolio_snapshots"] >= 1
    # Configuration kept
    assert response.data["kept"]["category_rules"] == rules_before
    # The database actually got wiped
    assert Account.objects.count() == 0
    assert Transaction.objects.count() == 0
    assert PortfolioSnapshot.objects.count() == 0
    assert BalanceSnapshot.objects.count() == 0
    assert StatementImport.objects.count() == 0
    # Rules and categories are still there
    assert CategoryRule.objects.count() == rules_before
    assert Category.objects.count() > 0


@pytest.mark.django_db
def test_reset_endpoint_requires_confirmation(api_client, seeded):
    """
    A reset call without the magic token returns 400 and leaves data alone.

    Args:
        api_client (APIClient): Authenticated client
        seeded (dict): Fixture data

    Returns:
        None
    """

    response = api_client.post("/api/reset/", data={"confirm": "no"}, format="json")
    assert response.status_code == 400
    # Nothing was deleted
    assert Account.objects.count() > 0
    assert Transaction.objects.count() > 0

    response = api_client.post("/api/reset/", data={}, format="json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_reset_endpoint_requires_authentication():
    """
    The reset endpoint rejects anonymous requests.

    Args:
        None

    Returns:
        None
    """

    response = APIClient().post("/api/reset/", data={"confirm": "RESET"}, format="json")
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_transactions_list_requires_authentication():
    """
    The transactions list rejects anonymous requests.

    Args:
        None

    Returns:
        None
    """

    response = APIClient().get("/api/transactions/")
    assert response.status_code in (401, 403)
