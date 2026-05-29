# Author: xhico
# Date: May 27, 2026
"""Tests for the Degiro cash-account CSV parser and importer."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from finance.models import Account, Transaction
from finance.parsers.degiro_csv import parse as parse_csv
from finance.services import DEGIRO_IBAN, import_degiro_csv

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    """
    Read a fixture file's text.

    Args:
        name (str): Fixture filename under the fixtures directory

    Returns:
        str: The fixture text
    """

    return (FIXTURES / name).read_text(encoding="utf-8")


def test_csv_parser_keeps_only_real_cash_movements_and_income():
    """
    The CSV parser drops sweeps, fees and ETF buys, keeping flatex deposits,
    processed withdrawals, dividends and interest income.

    Args:
        None

    Returns:
        None
    """

    parsed = parse_csv(_load("degiro_account_sample.csv"))

    # Two deposits, one withdrawal, one dividend, one interest row -> 5; the
    # fee and the buy row share dates with real movements but must not be kept.
    assert len(parsed.movements) == 5
    kinds = sorted(m.kind for m in parsed.movements)
    assert kinds == ["deposit", "deposit", "dividend", "interest", "withdrawal"]
    descriptions = [m.description for m in parsed.movements]
    assert not any("Compra" in d for d in descriptions)
    assert not any("Comissões" in d for d in descriptions)


def test_csv_parser_signs_wallet_flows_and_income_correctly():
    """
    Deposits flip into negative wallet amounts; withdrawals into positive.
    Dividend and interest income keep the broker's positive sign so they
    read as income arriving.

    Args:
        None

    Returns:
        None
    """

    parsed = parse_csv(_load("degiro_account_sample.csv"))
    by_date = {m.date: m for m in parsed.movements}
    # Deposit on 2026-02-05 (Mudança +100,00) -> wallet sees -100.00
    assert by_date[date(2026, 2, 5)].amount == Decimal("-100.00")
    # Withdrawal on 2026-01-15 (Mudança -50,00) -> wallet sees +50.00
    assert by_date[date(2026, 1, 15)].amount == Decimal("50.00")
    # Dividend and interest income keep the broker's positive sign
    assert by_date[date(2026, 2, 3)].amount == Decimal("7.50")
    assert by_date[date(2026, 2, 1)].amount == Decimal("0.15")


@pytest.mark.django_db
def test_import_degiro_csv_creates_per_deposit_transactions():
    """
    Importing the CSV creates Investment transactions for wallet flows and
    Investment-income transactions for dividends and interest.

    Args:
        None

    Returns:
        None
    """

    result = import_degiro_csv(_load("degiro_account_sample.csv"), source_file="Account.csv")

    assert result["movements"] == 5
    assert result["created"] == 5
    assert result["skipped"] == 0

    account = Account.objects.get(iban=DEGIRO_IBAN)
    assert account.name == "Degiro"
    assert account.scope == "personal"
    txns = Transaction.objects.filter(account=account)
    assert txns.count() == 5
    by_kind = {t.category.kind for t in txns}
    assert by_kind == {"investment", "income"}
    investment_rows = txns.filter(category__name="Investment")
    income_rows = txns.filter(category__name="Investment income")
    assert investment_rows.count() == 3
    assert income_rows.count() == 2
    assert all(t.category.kind == "income" for t in income_rows)


@pytest.mark.django_db
def test_import_degiro_csv_is_idempotent():
    """
    Re-importing the same CSV adds nothing.

    Args:
        None

    Returns:
        None
    """

    first = import_degiro_csv(_load("degiro_account_sample.csv"), source_file="Account.csv")
    second = import_degiro_csv(_load("degiro_account_sample.csv"), source_file="Account.csv")

    assert first["created"] == 5
    assert second["created"] == 0
    assert second["skipped"] == 5
    assert Transaction.objects.filter(account__iban=DEGIRO_IBAN).count() == 5
