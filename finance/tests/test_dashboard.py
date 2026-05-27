# Author: xhico
# Date: May 27, 2026
"""Tests for classification and the dashboard API."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from rest_framework.test import APIClient

from finance.models import Account, BalanceSnapshot, Category, CategoryRule, StatementImport, Transaction
from finance.services import classify_transactions, import_statement

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    """
    Read a fixture statement's text.

    Args:
        name (str): Fixture filename under the fixtures directory

    Returns:
        str: The fixture text
    """

    return (FIXTURES / name).read_text(encoding="utf-8")


def _make_rules():
    """
    Create a generic salary and internal-transfer rule for tests.

    Uses invented match strings so the tests never depend on real account data.

    Args:
        None

    Returns:
        tuple: The (salary, transfer) Category objects
    """

    salary = Category.objects.create(name="Salary", kind=Category.Kind.INCOME)
    transfer = Category.objects.create(name="Internal transfer", kind=Category.Kind.TRANSFER)
    CategoryRule.objects.create(
        match_text="ACME PAYROLL", sign=CategoryRule.Sign.CREDIT, scope="personal", category=salary, priority=10
    )
    CategoryRule.objects.create(match_text="VAULT MOVE", sign=CategoryRule.Sign.ANY, category=transfer, priority=20)
    return salary, transfer


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


@pytest.mark.django_db
def test_classification_buckets_income_and_transfers():
    """
    Rules classify a salary credit and an internal transfer.

    Args:
        None

    Returns:
        None
    """

    _make_rules()
    account = Account.objects.create(name="House", bank="Bank", iban="PT50000000000000000000009", scope="personal")
    salary = Transaction.objects.create(
        account=account, date=date(2026, 4, 30), description="ACME PAYROLL APR", amount=Decimal("1200.00")
    )
    transfer = Transaction.objects.create(
        account=account, date=date(2026, 4, 30), description="VAULT MOVE 123", amount=Decimal("-800.00")
    )

    classify_transactions()
    salary.refresh_from_db()
    transfer.refresh_from_db()

    assert salary.category.kind == "income"
    assert salary.category.name == "Salary"
    assert transfer.category.name == "Internal transfer"


@pytest.mark.django_db
def test_income_endpoint_sums_only_income(api_client):
    """
    The income endpoint sums income-categorised movements by month.

    Args:
        api_client (APIClient): Authenticated client fixture

    Returns:
        None
    """

    _make_rules()
    account = Account.objects.create(name="House", bank="Bank", iban="PT50000000000000000000009", scope="personal")
    # An income credit and an internal transfer in the same month
    Transaction.objects.create(
        account=account, date=date(2026, 4, 15), description="ACME PAYROLL", amount=Decimal("1000.00")
    )
    Transaction.objects.create(
        account=account, date=date(2026, 4, 16), description="VAULT MOVE", amount=Decimal("-500.00")
    )
    classify_transactions()

    response = api_client.get("/api/dashboard/income/")

    assert response.status_code == 200
    # Only the salary counts; the transfer is excluded
    assert response.data["monthly"] == [{"period": "2026-04", "income": 1000.0}]
    assert response.data["quarterly"] == [{"period": "2026-Q2", "income": 1000.0}]


@pytest.mark.django_db
def test_net_worth_endpoint_from_snapshot(api_client):
    """
    The net-worth endpoint derives net worth from a balance snapshot.

    Args:
        api_client (APIClient): Authenticated client fixture

    Returns:
        None
    """

    statement = StatementImport.objects.create(bank="cgd", scope="personal", period_end=date(2026, 4, 30))
    BalanceSnapshot.objects.create(
        statement=statement,
        as_of=date(2026, 4, 30),
        current_total=Decimal("1000.00"),
        savings_total=Decimal("5000.00"),
        investments_total=Decimal("0.00"),
        mortgage_balance=Decimal("100000.00"),
    )

    response = api_client.get("/api/dashboard/net-worth/")

    assert response.status_code == 200
    assert len(response.data) == 1
    entry = response.data[0]
    assert entry["savings"] == 5000.0
    # Net worth is assets minus the mortgage
    assert entry["net_worth"] == 1000.0 + 5000.0 + 0.0 - 100000.0


@pytest.mark.django_db
def test_dashboard_requires_authentication():
    """
    The dashboard endpoints reject anonymous requests.

    Args:
        None

    Returns:
        None
    """

    response = APIClient().get("/api/dashboard/income/")
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_seed_finance_loads_example_template():
    """
    Seeding with no private file falls back to the example template.

    Args:
        None

    Returns:
        None
    """

    example = Path(__file__).resolve().parents[2] / "seed_rules.example.json"
    call_command("seed_finance", file=str(example))

    assert Category.objects.filter(name="Salary", kind="income").exists()
    assert CategoryRule.objects.count() == 5
    # The example uses placeholder match strings, never real account data
    assert CategoryRule.objects.filter(match_text__startswith="EXAMPLE").count() == 5


@pytest.mark.django_db
def test_import_auto_classifies_with_rules():
    """
    Importing after rules exist classifies the new transactions.

    Args:
        None

    Returns:
        None
    """

    income = Category.objects.create(name="Salary", kind=Category.Kind.INCOME)
    CategoryRule.objects.create(match_text="EXAMPLE PAYER", sign=CategoryRule.Sign.CREDIT, category=income, priority=10)

    import_statement(_load("cgd_sample.txt"), source_file="cgd_sample.pdf")

    # The "TFI EXAMPLE PAYER" credit in the fixture is auto-classified on import
    matched = Transaction.objects.filter(category=income)
    assert matched.count() == 1
    assert "EXAMPLE PAYER" in matched.first().description
