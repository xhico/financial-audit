# Author: xhico
# Date: May 27, 2026
"""Tests for the statement parsers using synthetic fixture text."""

from decimal import Decimal
from pathlib import Path

from finance.parsers import detect_bank, parse

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


def _reconciles(account):
    """
    Check that each balance equals the previous balance plus the amount.

    Args:
        account (ParsedAccount): The account whose movements to verify

    Returns:
        bool: True when every movement reconciles against the opening balance
    """

    balance = account.opening_balance
    for txn in account.transactions:
        if balance is None or txn.balance is None:
            return False
        if (balance + txn.amount).quantize(Decimal("0.01")) != txn.balance:
            return False
        balance = txn.balance
    return True


def test_detect_bank_identifies_each_format():
    """
    Bank detection recognises both statement formats.

    Args:
        None

    Returns:
        None
    """

    assert detect_bank(_load("credito_agricola_sample.txt")) == "credito_agricola"
    assert detect_bank(_load("cgd_sample.txt")) == "cgd"


def test_credito_agricola_parses_and_reconciles():
    """
    The Crédito Agrícola parser derives signed amounts that reconcile.

    Args:
        None

    Returns:
        None
    """

    statement = parse(_load("credito_agricola_sample.txt"))

    assert statement.bank == "credito_agricola"
    assert statement.scope == "business"
    assert statement.statement_number == "004/2026"
    assert len(statement.accounts) == 1

    account = statement.accounts[0]
    assert account.iban == "PT50000000000000000000001"
    assert account.opening_balance == Decimal("1000.00")
    assert len(account.transactions) == 3

    # A debit is negative, credits are positive, derived from the balance change
    assert account.transactions[0].amount == Decimal("-100.00")
    assert account.transactions[2].amount == Decimal("2000.00")
    # The wrapped description is joined across the two source lines
    assert "UNIPESSOAL" in account.transactions[1].description
    assert _reconciles(account)


def test_cgd_parses_accounts_and_snapshot():
    """
    The CGD parser yields both current accounts and the summary snapshot.

    Args:
        None

    Returns:
        None
    """

    statement = parse(_load("cgd_sample.txt"))

    assert statement.bank == "cgd"
    assert statement.scope == "personal"
    assert statement.statement_number == "005/2026"
    assert len(statement.accounts) == 2

    first, second = statement.accounts
    assert first.iban == "PT50000000000000000000002"
    assert len(first.transactions) == 2
    assert first.transactions[0].amount == Decimal("-100.00")
    assert _reconciles(first)
    assert _reconciles(second)

    snapshot = statement.snapshot
    assert snapshot is not None
    assert snapshot.current_total == Decimal("1000.00")
    assert snapshot.savings_total == Decimal("5000.00")
    assert snapshot.mortgage_balance == Decimal("100000.00")
