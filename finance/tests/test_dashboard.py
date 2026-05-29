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

from finance.models import (
    Account,
    BalanceSnapshot,
    Category,
    CategoryRule,
    IgnoreRule,
    StatementImport,
    Transaction,
)
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
    # The response is now keyed by scope; the "all" view aggregates everything
    assert response.data["all"]["monthly"] == [{"period": "2026-04", "income": 1000.0}]
    assert response.data["all"]["quarterly"] == [{"period": "2026-Q2", "income": 1000.0}]


@pytest.mark.django_db
def test_net_worth_endpoint_from_snapshot(api_client):
    """
    The net-worth endpoint derives net worth from a balance snapshot.

    Args:
        api_client (APIClient): Authenticated client fixture

    Returns:
        None
    """

    savings = Decimal("10.00")
    mortgage = Decimal("100.00")
    statement = StatementImport.objects.create(bank="cgd", scope="personal", period_end=date(2026, 4, 30))
    BalanceSnapshot.objects.create(
        statement=statement,
        as_of=date(2026, 4, 30),
        current_total=Decimal("0.00"),
        savings_total=savings,
        investments_total=Decimal("0.00"),
        mortgage_balance=mortgage,
    )

    response = api_client.get("/api/dashboard/net-worth/")

    assert response.status_code == 200
    assert len(response.data) == 1
    entry = response.data[0]
    # No accounts in this fixture, so business / personal / house are all zero.
    # Mortgage is reported alongside but is no longer subtracted from net worth.
    assert entry["business"] == 0.0
    assert entry["personal"] == 0.0
    assert entry["house"] == 0.0
    assert entry["savings"] == float(savings)
    assert entry["mortgage"] == float(mortgage)
    # Net worth = business + personal + house + savings + investments (no mortgage)
    assert entry["net_worth"] == float(savings)


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
def test_category_rule_effective_from_only_matches_later_dates():
    """
    A rule with effective_from set only classifies transactions on or after it.

    Args:
        None

    Returns:
        None
    """

    investment = Category.objects.create(name="Investment", kind=Category.Kind.INVESTMENT)
    transfer = Category.objects.create(name="Internal transfer", kind=Category.Kind.TRANSFER)
    # Cut-off rule for 2026 onwards, plus a catch-all for everything before
    CategoryRule.objects.create(
        match_text="BROKER",
        sign=CategoryRule.Sign.ANY,
        category=investment,
        effective_from=date(2026, 1, 1),
        priority=15,
    )
    CategoryRule.objects.create(
        match_text="BROKER",
        sign=CategoryRule.Sign.ANY,
        category=transfer,
        priority=20,
    )

    account = Account.objects.create(name="House", bank="Bank", iban="PT50000000000000000000020", scope="personal")
    pre = Transaction.objects.create(
        account=account,
        date=date(2025, 6, 1),
        description="BROKER deposit",
        amount=Decimal("-500.00"),
    )
    post = Transaction.objects.create(
        account=account,
        date=date(2026, 2, 1),
        description="BROKER deposit",
        amount=Decimal("-500.00"),
    )

    classify_transactions()
    pre.refresh_from_db()
    post.refresh_from_db()

    assert pre.category.name == "Internal transfer"
    assert post.category.name == "Investment"


@pytest.mark.django_db
def test_seed_finance_updates_existing_rules_in_place(tmp_path):
    """
    Re-seeding with a different category for the same match maps the existing rule
    to the new category instead of creating a duplicate.

    Args:
        tmp_path (pathlib.Path): A temporary directory provided by pytest

    Returns:
        None
    """

    seed_first = {
        "categories": [{"name": "Salary", "kind": "income"}],
        "rules": [{"match_text": "ACME", "sign": "any", "scope": "", "category": "Salary", "priority": 20}],
    }
    seed_second = {
        "categories": [
            {"name": "Salary", "kind": "income"},
            {"name": "Internal transfer", "kind": "transfer"},
        ],
        "rules": [{"match_text": "ACME", "sign": "any", "scope": "", "category": "Internal transfer", "priority": 20}],
    }

    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    import json

    first_path.write_text(json.dumps(seed_first))
    second_path.write_text(json.dumps(seed_second))

    call_command("seed_finance", file=str(first_path))
    assert CategoryRule.objects.filter(match_text="ACME").count() == 1
    assert CategoryRule.objects.get(match_text="ACME").category.name == "Salary"

    call_command("seed_finance", file=str(second_path))
    # Still exactly one rule; the category moved to the new value
    assert CategoryRule.objects.filter(match_text="ACME").count() == 1
    assert CategoryRule.objects.get(match_text="ACME").category.name == "Internal transfer"


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
def test_ignore_rule_skips_matching_transactions():
    """
    Importing with an IgnoreRule drops matching rows entirely.

    Args:
        None

    Returns:
        None
    """

    IgnoreRule.objects.create(match_text="EXAMPLE INSURANCE", note="test")

    result = import_statement(_load("cgd_sample.txt"), source_file="cgd_sample.pdf")

    # The "EXAMPLE INSURANCE" debit in the fixture is dropped before insert
    assert not Transaction.objects.filter(description__icontains="EXAMPLE INSURANCE").exists()
    assert result.ignored >= 1


@pytest.mark.django_db
def test_seed_finance_creates_ignore_rules(tmp_path):
    """
    The seed command turns "ignore" entries into IgnoreRule rows and updates them in place.

    Args:
        tmp_path (pathlib.Path): A temporary directory provided by pytest

    Returns:
        None
    """

    import json

    seed_first = {
        "categories": [],
        "rules": [],
        "ignore": [{"match_text": "NOISY", "note": "first"}],
    }
    seed_second = {
        "categories": [],
        "rules": [],
        "ignore": [{"match_text": "NOISY", "note": "second"}],
    }

    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first_path.write_text(json.dumps(seed_first))
    second_path.write_text(json.dumps(seed_second))

    call_command("seed_finance", file=str(first_path))
    assert IgnoreRule.objects.filter(match_text="NOISY").count() == 1
    assert IgnoreRule.objects.get(match_text="NOISY").note == "first"

    call_command("seed_finance", file=str(second_path))
    # Still exactly one row; the note moved to the new value
    assert IgnoreRule.objects.filter(match_text="NOISY").count() == 1
    assert IgnoreRule.objects.get(match_text="NOISY").note == "second"


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
