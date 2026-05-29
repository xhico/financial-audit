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


def test_csv_parser_keeps_only_real_cash_movements():
    """
    The CSV parser drops sweeps, fees and ETF buys, keeping only flatex
    deposits and processed withdrawals.

    Args:
        None

    Returns:
        None
    """

    parsed = parse_csv(_load("degiro_account_sample.csv"))

    # Two deposits and one withdrawal in the fixture; the fee and the buy row
    # share dates with real cash movements but must not become transactions.
    assert len(parsed.movements) == 3
    descriptions = [m.description for m in parsed.movements]
    assert "flatex Deposit" in descriptions
    assert "Processed Flatex Withdrawal" in descriptions
    assert not any("Compra" in d for d in descriptions)
    assert not any("Comissões" in d for d in descriptions)


def test_csv_parser_flips_sign_to_wallet_perspective():
    """
    A deposit shows as a negative wallet amount; a withdrawal as positive.

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


@pytest.mark.django_db
def test_import_degiro_csv_creates_per_deposit_transactions():
    """
    Importing the CSV creates one Investment transaction per cash movement.

    Args:
        None

    Returns:
        None
    """

    result = import_degiro_csv(_load("degiro_account_sample.csv"), source_file="Account.csv")

    assert result["movements"] == 3
    assert result["created"] == 3
    assert result["skipped"] == 0

    account = Account.objects.get(iban=DEGIRO_IBAN)
    assert account.name == "Degiro"
    assert account.scope == "personal"
    txns = Transaction.objects.filter(account=account)
    assert txns.count() == 3
    assert all(t.category.name == "Investment" for t in txns)
    assert all(t.category.kind == "investment" for t in txns)


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

    assert first["created"] == 3
    assert second["created"] == 0
    assert second["skipped"] == 3
    assert Transaction.objects.filter(account__iban=DEGIRO_IBAN).count() == 3
