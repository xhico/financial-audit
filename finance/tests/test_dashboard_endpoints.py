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
