# Author: xhico
# Date: May 27, 2026
"""Tests for the expanded dashboard API: expenses, cashflow, overview, accounts, transactions."""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from finance.models import Account, BalanceSnapshot, Category, CategoryRule, StatementImport, Transaction
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

    # Personal current account with an income credit and an expense debit
    house = Account.objects.create(name="House", bank="Bank", iban="PT50000000000000000000010", scope="personal")
    # Business current account with a tax payment
    biz = Account.objects.create(name="Business", bank="Bank", iban="PT50000000000000000000011", scope="business")

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
    # April had 100 in Groceries and 200 in Tax = 300 of money out
    assert {"period": "2026-04", "total": 300.0} in body["monthly"]
    categories = {row["category"]: row["total"] for row in body["by_category"]}
    assert categories["Groceries"] == 100.0
    assert categories["Tax"] == 200.0
    assert {"period": "2026-04", "category": "Groceries", "total": 100.0} in body["monthly_by_category"]


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
    months = {row["period"]: row for row in response.data}
    # April: income 1500, expenses 300, net 1200
    assert months["2026-04"]["income"] == 1500.0
    assert months["2026-04"]["expenses"] == 300.0
    assert months["2026-04"]["net"] == 1200.0
    # March: income 1500, no expenses
    assert months["2026-03"]["income"] == 1500.0
    assert months["2026-03"]["expenses"] == 0.0


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
    assert body["net_worth"]["savings"] == 5000.0
    assert body["net_worth"]["net_worth"] == 1000.0 + 5000.0 + 0.0 - 100000.0


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
