# Author: xhico
# Date: May 29, 2026
"""
Parser for the Degiro Conta Caixa CSV export ("Account.csv").

The Degiro web portal exports every cash-account movement for a chosen
date range as a CSV. Only two row types matter for a personal finance
ledger: the bank-to-flatex deposits the user funds and the flatex-to-bank
withdrawals they take back. Everything else (sweeps between the cash and
investment legs, ETF buys, fees, dividends, FX, interest) is internal to
the broker and does not move money in or out of the user's wallet.
"""

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

# Description substrings (matched case-insensitively) used to classify each
# CSV row into one of four kinds we care about. Everything else (sweeps,
# fees, ETF orders, FX) is internal to the broker and gets dropped.
DEPOSIT_PATTERNS = ("flatex deposit",)
# Degiro emits two variants for cash going back to the user's bank: the
# settled "flatex Withdrawal" row, and the bookkeeping "Processed Flatex
# Withdrawal" pair. The substring catches both since "flatex withdrawal"
# is also in "Processed Flatex Withdrawal".
WITHDRAWAL_PATTERNS = ("flatex withdrawal",)
DIVIDEND_PATTERNS = ("dividendo",)
INTEREST_PATTERNS = ("flatex interest income",)

# Movement kinds that change the user's wallet vs that earn income inside
# the broker. The sign convention for amount differs between the two:
# wallet-side rows are flipped (deposit = negative wallet flow) while
# broker-side income keeps the broker's positive sign so it reads as
# income on the dashboards.
WALLET_KINDS = ("deposit", "withdrawal")
INCOME_KINDS = ("dividend", "interest")


def _parse_date(token):
    """
    Parse a Degiro CSV date in DD-MM-YYYY format.

    Args:
        token (str): The date string, e.g. "07-04-2026"

    Returns:
        datetime.date: The parsed date
    """

    return datetime.strptime(token.strip(), "%d-%m-%Y").date()


def _parse_amount(token):
    """
    Parse a Portuguese-formatted Degiro amount into a Decimal.

    Args:
        token (str): The money string, e.g. "1 050,00", "500,00", "-137,93"

    Returns:
        Decimal: The parsed value, or Decimal("0") for empty strings
    """

    cleaned = (token or "").strip().replace("\xa0", "").replace(" ", "").replace(".", "").replace(",", ".")
    if not cleaned:
        return Decimal("0")
    return Decimal(cleaned)


@dataclass
class ParsedDegiroMovement:
    """
    A single cash-account movement worth recording in the ledger.

    - Captures the value date, description, signed amount and balance
    - kind disambiguates wallet flows (deposit / withdrawal) from
      broker-side income (dividend / interest); the importer maps that
      onto a category
    - Sign convention is tied to kind: wallet flows flip Mudança so a
      deposit (bank -> Degiro) shows as a negative wallet amount; broker
      income keeps the broker's positive sign so dashboards read it as
      income arriving
    """

    date: object
    description: str
    amount: Decimal
    balance: Decimal
    kind: str


@dataclass
class ParsedDegiroAccountCsv:
    """
    The cash movements extracted from one Degiro CSV export.

    - movements: every deposit and withdrawal in the file
    """

    movements: list = field(default_factory=list)


def parse(text):
    """
    Parse a Degiro Account.csv into the cash movements that affect the wallet.

    Skips header, non-cash rows (sweeps, fees, ETF orders, interest, FX,
    dividends) and any row whose change column is empty.

    Args:
        text (str): The CSV text. The file is small enough to read in full
            and pass in as a string.

    Returns:
        ParsedDegiroAccountCsv: The list of relevant movements
    """

    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if not header or header[0].strip().lower() != "data":
        raise ValueError("CSV does not look like a Degiro Account.csv export (missing 'Data' header)")

    movements = []
    for row in reader:
        # The header has 12 columns; pad short rows so indexing is safe
        if len(row) < 12:
            row = row + [""] * (12 - len(row))

        description = (row[5] or "").strip()
        description_lower = description.lower()
        kind = None
        if any(pattern in description_lower for pattern in DEPOSIT_PATTERNS):
            kind = "deposit"
        elif any(pattern in description_lower for pattern in WITHDRAWAL_PATTERNS):
            kind = "withdrawal"
        elif any(pattern in description_lower for pattern in DIVIDEND_PATTERNS):
            kind = "dividend"
        elif any(pattern in description_lower for pattern in INTEREST_PATTERNS):
            kind = "interest"
        if kind is None:
            continue

        change_raw = row[8]
        if not change_raw.strip():
            continue

        # The CSV's "Mudança" tracks the flatex balance. For wallet flows we
        # flip the sign so a deposit reads as money leaving the wallet; for
        # broker-side income we keep the broker's positive sign so dashboards
        # show the dividend / interest as income arriving.
        change = _parse_amount(change_raw)
        if kind in WALLET_KINDS:
            amount = -change
        else:
            amount = change

        balance = _parse_amount(row[10]) if row[10].strip() else None
        date = _parse_date(row[0])

        movements.append(
            ParsedDegiroMovement(
                date=date,
                description=description,
                amount=amount,
                balance=balance,
                kind=kind,
            )
        )

    return ParsedDegiroAccountCsv(movements=movements)
