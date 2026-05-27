# Author: xhico
# Date: May 27, 2026
"""Tests for the statement import service."""

from decimal import Decimal
from pathlib import Path

import pytest

from finance.models import Account, BalanceSnapshot, StatementImport, Transaction
from finance.services import import_statement

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


@pytest.mark.django_db
def test_import_creates_accounts_transactions_and_snapshot():
    """
    Importing a CGD statement creates its accounts, movements and snapshot.

    Args:
        None

    Returns:
        None
    """

    result = import_statement(_load("cgd_sample.txt"), source_file="cgd_sample.pdf")

    assert Account.objects.count() == 2
    assert Transaction.objects.count() == 4
    assert result.created == 4
    assert result.skipped == 0

    statement = result.statement
    assert statement.scope == "personal"
    snapshot = BalanceSnapshot.objects.get(statement=statement)
    assert snapshot.savings_total == Decimal("5000.00")
    assert snapshot.mortgage_balance == Decimal("100000.00")


@pytest.mark.django_db
def test_reimport_is_idempotent():
    """
    Re-importing the same statement adds nothing and reuses the records.

    Args:
        None

    Returns:
        None
    """

    first = import_statement(_load("cgd_sample.txt"), source_file="cgd_sample.pdf")
    second = import_statement(_load("cgd_sample.txt"), source_file="cgd_sample.pdf")

    assert first.created == 4
    assert second.created == 0
    assert second.skipped == 4
    # No duplicate accounts, transactions or statement records were made
    assert Account.objects.count() == 2
    assert Transaction.objects.count() == 4
    assert StatementImport.objects.count() == 1


@pytest.mark.django_db
def test_import_business_statement_signs_amounts():
    """
    A Crédito Agrícola import stores debits as negative and credits as positive.

    Args:
        None

    Returns:
        None
    """

    import_statement(_load("credito_agricola_sample.txt"), source_file="ca.pdf")

    account = Account.objects.get(scope="business")
    amounts = list(account.transactions.order_by("date").values_list("amount", flat=True))
    assert amounts[0] == Decimal("-100.00")
    assert amounts[-1] == Decimal("2000.00")
