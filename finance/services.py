# Author: xhico
# Date: May 27, 2026
"""
Import services for the finance app.

Turns the normalised output of the statement parsers into ORM records. Kept
separate from the management command and the (future) upload view so both share
one idempotent code path.
"""

from dataclasses import dataclass
from datetime import date

from django.db import transaction

from finance.models import (
    Account,
    BalanceSnapshot,
    Category,
    CategoryRule,
    IgnoreRule,
    StatementImport,
    Transaction,
)
from finance.parsers import degiro as degiro_parser
from finance.parsers import parse

# Synthetic IBAN for the Degiro Cash Account; not a real PT IBAN since the
# broker is German-domiciled, but stable so the account is reused across imports
DEGIRO_IBAN = "DEGIROCASHACCOUNT"

# Maps the parser bank key onto a readable bank name for the Account
BANK_NAMES = {
    "credito_agricola": "Crédito Agrícola",
    "cgd": "Caixa Geral de Depósitos",
}


@dataclass
class ImportResult:
    """
    The outcome of importing one statement.

    - Reports how many transactions were created versus already present
    - Counts rows dropped by an IgnoreRule separately from re-imports
    - Carries the statement and the accounts it touched
    """

    statement: StatementImport
    created: int
    skipped: int
    accounts: list
    ignored: int = 0


def _account_name(parsed_account):
    """
    Build a stable display name for an account from its parsed data.

    Args:
        parsed_account (ParsedAccount): The parsed account

    Returns:
        str: A name including the last four IBAN digits when available
    """

    # Suffix the last four IBAN characters so the two CGD current accounts differ
    suffix = parsed_account.iban[-4:] if parsed_account.iban else ""
    return f"{parsed_account.name} {suffix}".strip()


@transaction.atomic
def import_statement(text, source_file=""):
    """
    Import a statement's text into accounts, transactions and a snapshot.

    Re-importing the same statement is safe: accounts and the statement record
    are reused, and transactions collapse onto their dedupe key.

    Args:
        text (str): The extracted statement text
        source_file (str): Original filename, stored for traceability

    Returns:
        ImportResult: Counts and the records touched

    Raises:
        ValueError: When the statement format is not recognised
    """

    parsed = parse(text)

    # Reuse the statement record when this exact statement was imported before
    lookup = {"bank": parsed.bank}
    if parsed.statement_number:
        lookup["statement_number"] = parsed.statement_number
    else:
        lookup["period_start"] = parsed.period_start
        lookup["period_end"] = parsed.period_end
    statement, _ = StatementImport.objects.get_or_create(
        defaults={
            "scope": parsed.scope,
            "period_start": parsed.period_start,
            "period_end": parsed.period_end,
            "source_file": source_file,
        },
        **lookup,
    )

    # Patterns whose matching rows should never enter the ledger (e.g. the
    # bank-side mirror of a broker deposit, where the real movement is tracked
    # in a separate import path)
    ignore_patterns = [p.lower() for p in IgnoreRule.objects.values_list("match_text", flat=True)]

    created = 0
    skipped = 0
    ignored = 0
    touched_accounts = []
    for parsed_account in parsed.accounts:
        if not parsed_account.iban:
            continue
        account, _ = Account.objects.get_or_create(
            iban=parsed_account.iban,
            defaults={
                "name": _account_name(parsed_account),
                "bank": BANK_NAMES.get(parsed.bank, parsed.bank),
                "scope": parsed.scope,
                "kind": parsed_account.kind,
            },
        )
        touched_accounts.append(account)

        for txn in parsed_account.transactions:
            description_lower = txn.description.lower()
            if any(pattern in description_lower for pattern in ignore_patterns):
                ignored += 1
                continue
            key = Transaction.build_dedupe_key(account.id, txn.date, txn.description, txn.amount, txn.balance)
            _, was_created = Transaction.objects.get_or_create(
                dedupe_key=key,
                defaults={
                    "account": account,
                    "statement": statement,
                    "date": txn.date,
                    "value_date": txn.value_date,
                    "description": txn.description,
                    "amount": txn.amount,
                    "balance": txn.balance,
                },
            )
            if was_created:
                created += 1
            else:
                skipped += 1

    # Store (or refresh) the headline balances when the statement carries them
    if parsed.snapshot:
        s = parsed.snapshot
        BalanceSnapshot.objects.update_or_create(
            statement=statement,
            defaults={
                "as_of": s.as_of,
                "current_total": s.current_total,
                "savings_total": s.savings_total,
                "investments_total": s.investments_total,
                "mortgage_balance": s.mortgage_balance,
            },
        )

    # Classify the statement's transactions so the dashboards see them bucketed
    classify_transactions(statement.transactions.all())

    return ImportResult(
        statement=statement, created=created, skipped=skipped, accounts=touched_accounts, ignored=ignored
    )


@transaction.atomic
def import_degiro_report(text, source_file=""):
    """
    Import a Degiro annual report's net flow as a single Investment movement.

    Creates (or reuses) the Degiro Cash Account and inserts one transaction
    per year representing the net deposits, dated December 31 of that year.
    Re-importing the same report is safe; the dedupe key absorbs it.

    Args:
        text (str): The extracted report text
        source_file (str): Original filename, kept for traceability

    Returns:
        dict: Summary including the year, parsed figures and whether the
        transaction was newly created or skipped

    Raises:
        ValueError: When the report cannot be parsed
    """

    parsed = degiro_parser.parse(text)

    # Reuse one Degiro account across imports, owned personally by the user
    account, _ = Account.objects.get_or_create(
        iban=DEGIRO_IBAN,
        defaults={
            "name": "Degiro",
            "bank": "flatexDEGIRO Bank",
            "scope": Account.Scope.PERSONAL,
            "role": Account.Role.PERSONAL,
            "kind": Account.Kind.TERM,
        },
    )
    investment_cat, _ = Category.objects.get_or_create(name="Investment", defaults={"kind": Category.Kind.INVESTMENT})

    # Bank-side perspective: a net deposit reads as negative (money leaving
    # the user's bank to land at the broker)
    year_end = date(parsed.year, 12, 31)
    net = parsed.deposits - parsed.withdrawals
    description = f"Annual movement {parsed.year}: deposits €{parsed.deposits}, withdrawals €{parsed.withdrawals}"
    amount = -net

    key = Transaction.build_dedupe_key(account.id, year_end, description, amount, None)
    _, was_created = Transaction.objects.get_or_create(
        dedupe_key=key,
        defaults={
            "account": account,
            "date": year_end,
            "description": description,
            "amount": amount,
            "balance": None,
            "category": investment_cat,
        },
    )

    return {
        "year": parsed.year,
        "account": account,
        "deposits": parsed.deposits,
        "withdrawals": parsed.withdrawals,
        "net": net,
        "created": 1 if was_created else 0,
        "skipped": 0 if was_created else 1,
    }


def classify_transactions(transactions=None):
    """
    Assign categories to transactions using the ordered category rules.

    Args:
        transactions (QuerySet | None): Transactions to classify; all when None

    Returns:
        int: The number of transactions whose category changed
    """

    rules = list(CategoryRule.objects.select_related("category"))
    if not rules:
        return 0

    queryset = transactions if transactions is not None else Transaction.objects.all()

    updated = 0
    for txn in queryset.select_related("account"):
        # The rules are priority-ordered, so the first match wins
        for rule in rules:
            if rule.matches(txn):
                if txn.category_id != rule.category_id:
                    txn.category_id = rule.category_id
                    txn.save(update_fields=["category"])
                    updated += 1
                break
    return updated
