# Author: xhico
# Date: May 27, 2026
"""
Parser for Crédito Agrícola business statements ("Extracto de Conta").

The statement covers a single account. Each movement line carries two dates,
a description and two money values: the debit-or-credit magnitude and the
running balance. The signed amount is derived from the change in balance, which
also validates the parse.
"""

import re
from datetime import datetime
from decimal import Decimal

from finance.parsers.base import (
    ISO_DATE_RE,
    MONEY_RE,
    ParsedAccount,
    ParsedStatement,
    ParsedTransaction,
    normalise_iban,
    parse_amount,
)

# A movement line starts with the posting date and the value date
TXN_START_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+(\d{4}-\d{2}-\d{2})\s+(.*)$")
IBAN_RE = re.compile(r"IBAN\s*:?\s*(PT\d[\d ]{20,30}\d)")
STATEMENT_RE = re.compile(r"Extracto\s*:?\s*(\d+/\d+)")
OPENING_RE = re.compile(r"Saldo em\s+\d{2}-\d{2}-\d{4}\s+(" + MONEY_RE.pattern + r")")


def _to_date(token):
    """
    Convert an ISO date token into a date.

    Args:
        token (str): A date such as "2026-04-03"

    Returns:
        datetime.date: The parsed date
    """

    return datetime.strptime(token, "%Y-%m-%d").date()


def parse(text):
    """
    Parse a Crédito Agrícola statement into a ParsedStatement.

    Args:
        text (str): The extracted statement text

    Returns:
        ParsedStatement: A single business account with its movements

    Process:
        Find the IBAN and opening balance, group movement lines (joining any
        wrapped continuation lines), then derive each signed amount from the
        running balance.
    """

    lines = [ln.strip() for ln in text.replace("\f", "\n").splitlines()]

    # Pull the account IBAN and the opening balance from the header
    iban = ""
    opening = None
    statement_number = ""
    for ln in lines:
        if not iban:
            m = IBAN_RE.search(ln)
            if m:
                iban = normalise_iban(m.group(1))
        if not statement_number:
            m = STATEMENT_RE.search(ln)
            if m:
                statement_number = m.group(1)
        if opening is None:
            m = OPENING_RE.search(ln)
            if m:
                opening = parse_amount(m.group(1))

    # Group movement lines: a line starting with two dates begins a movement,
    # and any following line without a leading date continues its description
    groups = []
    for ln in lines:
        if TXN_START_RE.match(ln):
            groups.append([ln])
        elif groups and ln and not ISO_DATE_RE.match(ln):
            # Continuation lines only matter until the two trailing amounts appear
            if len(MONEY_RE.findall(" ".join(groups[-1]))) < 2:
                groups[-1].append(ln)

    transactions = []
    prev_balance = opening
    for group in groups:
        joined = " ".join(group)
        m = TXN_START_RE.match(group[0])
        post_date = _to_date(m.group(1))
        value_date = _to_date(m.group(2))

        monies = MONEY_RE.findall(joined)
        # A complete movement ends with the magnitude and the running balance
        if len(monies) < 2:
            continue
        balance = parse_amount(monies[-1])

        # Everything between the second date and the first trailing amount is text
        body = joined[m.start(3) :]
        cut = body.rfind(monies[-1])
        cut = body.rfind(monies[-2], 0, cut)
        description = re.sub(r"\s+", " ", body[:cut]).strip()

        # Derive the signed amount from the balance change; fall back to the
        # printed magnitude when no opening balance was found
        if prev_balance is not None:
            amount = balance - prev_balance
        else:
            amount = parse_amount(monies[-2])
        prev_balance = balance

        transactions.append(
            ParsedTransaction(
                date=post_date,
                value_date=value_date,
                description=description,
                amount=amount.quantize(Decimal("0.01")),
                balance=balance,
            )
        )

    period_start = min((t.date for t in transactions), default=None)
    period_end = max((t.date for t in transactions), default=None)

    account = ParsedAccount(
        iban=iban,
        name="Conta Negócio",
        kind="current",
        opening_balance=opening,
        transactions=transactions,
    )
    return ParsedStatement(
        bank="credito_agricola",
        scope="business",
        statement_number=statement_number,
        period_start=period_start,
        period_end=period_end,
        accounts=[account],
    )
