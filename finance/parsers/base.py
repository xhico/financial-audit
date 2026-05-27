# Author: xhico
# Date: May 27, 2026
"""
Shared helpers and data structures for the statement parsers.

Holds the normalised result types, the Portuguese amount/IBAN helpers, the
pdfplumber text extraction and the bank-detection + dispatch entry points.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

# Matches a Portuguese-formatted money value, optionally signed: 1.234,56 / -19,46
MONEY_RE = re.compile(r"-?\d{1,3}(?:\.\d{3})*,\d{2}")
ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass
class ParsedTransaction:
    """
    A single movement extracted from a statement.

    - Carries the signed amount and the running balance after it
    - Dates are the posting date and the bank value date
    """

    date: date
    description: str
    amount: Decimal
    balance: Decimal | None = None
    value_date: date | None = None


@dataclass
class ParsedAccount:
    """
    An account discovered inside a statement, with its movements.

    - Identified by its normalised IBAN
    - Holds the opening balance used to reconcile signs
    """

    iban: str
    name: str
    kind: str
    opening_balance: Decimal | None = None
    transactions: list = field(default_factory=list)


@dataclass
class ParsedSnapshot:
    """
    The headline balances printed in a statement summary.

    - Optional; only the CGD global statement carries it
    - Feeds the savings and net-worth trends directly
    """

    as_of: date
    current_total: Decimal | None = None
    savings_total: Decimal | None = None
    investments_total: Decimal | None = None
    mortgage_balance: Decimal | None = None


@dataclass
class ParsedStatement:
    """
    The normalised result of parsing one statement PDF.

    - Groups the accounts and their transactions
    - Carries the period, statement number and optional summary snapshot
    """

    bank: str
    scope: str
    statement_number: str = ""
    period_start: date | None = None
    period_end: date | None = None
    accounts: list = field(default_factory=list)
    snapshot: ParsedSnapshot | None = None


def parse_amount(token):
    """
    Convert a Portuguese-formatted money token into a Decimal.

    Args:
        token (str): A value such as "1.234,56" or "-19,46"

    Returns:
        Decimal: The numeric value, sign preserved
    """

    # Drop thousands separators, then swap the decimal comma for a dot
    cleaned = token.strip().replace(".", "").replace(",", ".")
    return Decimal(cleaned)


def normalise_iban(raw):
    """
    Normalise an IBAN by removing spaces and upper-casing it.

    Args:
        raw (str): An IBAN possibly containing spaces

    Returns:
        str: The compact IBAN
    """

    return raw.replace(" ", "").strip().upper()


def extract_text(pdf_path):
    """
    Extract the text of a PDF as a single newline-joined string.

    Uses pdfplumber so extraction works inside the container without any
    system binaries. Falls back to an empty page rather than raising when a
    page yields no text.

    Args:
        pdf_path (str): Path to the PDF file

    Returns:
        str: The extracted text, pages separated by form feeds

    Raises:
        ImportError: When pdfplumber is not installed
    """

    import pdfplumber

    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return "\f".join(pages)


def detect_bank(text):
    """
    Identify which bank produced a statement from its text.

    Args:
        text (str): The extracted statement text

    Returns:
        str | None: "credito_agricola", "cgd", or None when unrecognised
    """

    # Match on stable issuer strings present in the header of each format
    if "creditoagricola" in text.lower() or "EXTRACTO DE CONTA" in text:
        return "credito_agricola"
    if "Extrato Global" in text or "CGDIPTPL" in text:
        return "cgd"
    return None


def parse(text):
    """
    Parse statement text into a ParsedStatement by dispatching on the bank.

    Args:
        text (str): The extracted statement text

    Returns:
        ParsedStatement: The normalised result

    Raises:
        ValueError: When the bank cannot be identified
    """

    # Import lazily to avoid a circular import at module load time
    from finance.parsers import cgd, credito_agricola

    bank = detect_bank(text)
    if bank == "credito_agricola":
        return credito_agricola.parse(text)
    if bank == "cgd":
        return cgd.parse(text)
    raise ValueError("Unrecognised statement format")
