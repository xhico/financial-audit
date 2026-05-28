# Author: xhico
# Date: May 27, 2026
"""Tests for the Degiro annual-report parser and importer."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from finance.models import Account, Transaction
from finance.parsers.degiro import parse
from finance.services import DEGIRO_IBAN, import_degiro_report

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    """
    Read a fixture report's text.

    Args:
        name (str): Fixture filename under the fixtures directory

    Returns:
        str: The fixture text
    """

    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parses_year_deposits_and_withdrawals():
    """
    The parser extracts the year, total deposits and total withdrawals.

    Args:
        None

    Returns:
        None
    """

    report = parse(_load("degiro_report_sample.txt"))
    assert report.year == 2024
    assert report.deposits == Decimal("4500.00")
    assert report.withdrawals == Decimal("200.00")


@pytest.mark.django_db
def test_import_creates_degiro_account_and_yearly_movement():
    """
    Importing a report creates the Degiro account and one yearly movement.

    Args:
        None

    Returns:
        None
    """

    result = import_degiro_report(_load("degiro_report_sample.txt"), source_file="report.pdf")

    assert result["year"] == 2024
    assert result["created"] == 1
    assert result["skipped"] == 0
    assert result["net"] == Decimal("4300.00")

    account = Account.objects.get(iban=DEGIRO_IBAN)
    assert account.name == "Degiro"
    assert account.scope == "personal"

    txn = Transaction.objects.get(account=account, date=date(2024, 12, 31))
    # Bank-side perspective: net deposit lands as negative
    assert txn.amount == Decimal("-4300.00")
    assert txn.category.name == "Investment"
    assert txn.category.kind == "investment"


@pytest.mark.django_db
def test_reimport_is_idempotent():
    """
    Re-importing the same report adds nothing.

    Args:
        None

    Returns:
        None
    """

    first = import_degiro_report(_load("degiro_report_sample.txt"), source_file="r.pdf")
    second = import_degiro_report(_load("degiro_report_sample.txt"), source_file="r.pdf")

    assert first["created"] == 1
    assert second["created"] == 0
    assert second["skipped"] == 1
    assert Transaction.objects.filter(account__iban=DEGIRO_IBAN).count() == 1
