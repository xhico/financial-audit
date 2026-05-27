# Author: xhico
# Date: May 27, 2026
"""
Parser for CGD "Extrato Global" household statements.

The global statement bundles several accounts. This parser extracts the current
("À Ordem") accounts and their movements, plus the headline summary balances
(current, savings, investments, mortgage). The savings sub-ledger, the mortgage
amortisation detail and the direct-debit mandate list are intentionally skipped,
since the summary already carries the figures the dashboards need.
"""

import re
from datetime import datetime
from decimal import Decimal

from finance.parsers.base import (
    MONEY_RE,
    ParsedAccount,
    ParsedSnapshot,
    ParsedStatement,
    ParsedTransaction,
    normalise_iban,
    parse_amount,
)

M = MONEY_RE.pattern
TXN_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+(\d{4}-\d{2}-\d{2})\s+(.*?)\s+(" + M + r")\s+(" + M + r")$")
SECTION_RE = re.compile(r"^CONTA EXTRACTO\b")
IBAN_RE = re.compile(r"IBAN\s+(PT\d{23})")
OPENING_RE = re.compile(r"Saldo anterior\s+(" + M + r")")
CLOSE_RE = re.compile(r"^Saldo (?:contabilístico|disponível)\b")
STATEMENT_RE = re.compile(r"Extrato n\.º\s*(\d+/\d+)")
PERIOD_RE = re.compile(r"Período\s+(\d{4}-\d{2}-\d{2})\s+a\s+(\d{4}-\d{2}-\d{2})")
MORTGAGE_RE = re.compile(r"Crédito Imobiliário\s+(" + M + r")")


def _to_date(token):
    """
    Convert an ISO date token into a date.

    Args:
        token (str): A date such as "2026-04-01"

    Returns:
        datetime.date: The parsed date
    """

    return datetime.strptime(token, "%Y-%m-%d").date()


def _label_value(line, label):
    """
    Return the first money value following a label on a line.

    Args:
        line (str): The text line
        label (str): The label preceding the value (e.g. "À Ordem")

    Returns:
        Decimal | None: The value, or None when the label is absent
    """

    if label not in line:
        return None
    tail = line.split(label, 1)[1]
    m = MONEY_RE.search(tail)
    return parse_amount(m.group(0)) if m else None


def parse(text):
    """
    Parse a CGD global statement into a ParsedStatement.

    Args:
        text (str): The extracted statement text

    Returns:
        ParsedStatement: The current accounts, movements and summary snapshot

    Process:
        Read the period and summary, then walk the account sections, collecting
        movement lines between each "CONTA EXTRACTO" header and its closing
        balance line.
    """

    lines = [ln.strip() for ln in text.replace("\f", "\n").splitlines()]

    statement_number = ""
    period_start = None
    period_end = None
    current_total = None
    savings_total = None
    investments_total = None
    mortgage_balance = None
    for ln in lines:
        if not statement_number:
            m = STATEMENT_RE.search(ln)
            if m:
                statement_number = m.group(1)
        if period_start is None:
            m = PERIOD_RE.search(ln)
            if m:
                period_start = _to_date(m.group(1))
                period_end = _to_date(m.group(2))
        # The summary prints each headline balance after its label
        if current_total is None and ln.startswith("À Ordem"):
            current_total = _label_value(ln, "À Ordem")
        if savings_total is None and ln.startswith("A Prazo/Poupança"):
            savings_total = _label_value(ln, "A Prazo/Poupança")
        if investments_total is None and ln.startswith("Instrumentos financeiros"):
            investments_total = _label_value(ln, "Instrumentos financeiros")
        if mortgage_balance is None:
            m = MORTGAGE_RE.search(ln)
            if m:
                mortgage_balance = parse_amount(m.group(1))

    # Walk the current-account sections and collect their movements
    accounts = []
    current = None
    in_section = False
    for ln in lines:
        if SECTION_RE.match(ln):
            in_section = True
            current = ParsedAccount(iban="", name="Conta à Ordem", kind="current", transactions=[])
            accounts.append(current)
            continue
        if not in_section or current is None:
            continue
        if not current.iban:
            m = IBAN_RE.search(ln)
            if m:
                current.iban = normalise_iban(m.group(1))
        if current.opening_balance is None:
            m = OPENING_RE.search(ln)
            if m:
                current.opening_balance = parse_amount(m.group(1))
        if CLOSE_RE.match(ln):
            in_section = False
            continue
        m = TXN_RE.match(ln)
        if m:
            amount = parse_amount(m.group(4))
            balance = parse_amount(m.group(5))
            current.transactions.append(
                ParsedTransaction(
                    date=_to_date(m.group(1)),
                    value_date=_to_date(m.group(2)),
                    description=re.sub(r"\s+", " ", m.group(3)).strip(),
                    amount=amount.quantize(Decimal("0.01")),
                    balance=balance,
                )
            )

    # Drop any section that yielded no IBAN and no movements (header artefacts)
    accounts = [a for a in accounts if a.iban or a.transactions]

    snapshot = None
    if period_end and any(v is not None for v in (current_total, savings_total, investments_total, mortgage_balance)):
        snapshot = ParsedSnapshot(
            as_of=period_end,
            current_total=current_total,
            savings_total=savings_total,
            investments_total=investments_total,
            mortgage_balance=mortgage_balance,
        )

    return ParsedStatement(
        bank="cgd",
        scope="personal",
        statement_number=statement_number,
        period_start=period_start,
        period_end=period_end,
        accounts=accounts,
        snapshot=snapshot,
    )
