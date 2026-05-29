# Author: xhico
# Date: May 27, 2026
"""
Import services for the finance app.

Turns the normalised output of the statement parsers into ORM records. Kept
separate from the management command and the (future) upload view so both share
one idempotent code path.
"""

from dataclasses import dataclass

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
from finance.parsers import degiro_csv as degiro_csv_parser
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
        # Derive the role from the account's scope at creation time. Business
        # scope implies the BUSINESS role; personal scope defaults to PERSONAL
        # and may be promoted to HOUSE further down once Mortgage transactions
        # have been classified.
        initial_role = Account.Role.BUSINESS if parsed.scope == Account.Scope.BUSINESS else Account.Role.PERSONAL
        account, _ = Account.objects.get_or_create(
            iban=parsed_account.iban,
            defaults={
                "name": _account_name(parsed_account),
                "bank": BANK_NAMES.get(parsed.bank, parsed.bank),
                "scope": parsed.scope,
                "role": initial_role,
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

    # Promote any personal-scope account whose ledger contains a Mortgage
    # movement to the HOUSE role. Mirrors the one-off backfill in migration
    # 0004 so re-imports after a wipe end up with the same tagging.
    _promote_household_accounts()

    return ImportResult(
        statement=statement, created=created, skipped=skipped, accounts=touched_accounts, ignored=ignored
    )


@transaction.atomic
def import_degiro_csv(text, source_file=""):
    """
    Import a Degiro Account.csv as per-deposit Investment transactions.

    Creates (or reuses) the Degiro Cash Account, parses every deposit and
    withdrawal from the export and inserts one transaction each, all
    classified as Investment. The dedupe key absorbs re-imports of the
    same export.

    Args:
        text (str): The CSV text
        source_file (str): Original filename, kept for traceability

    Returns:
        dict: Summary including counts and the account touched

    Raises:
        ValueError: When the file does not look like a Degiro account export
    """

    parsed = degiro_csv_parser.parse(text)

    account, _ = Account.objects.get_or_create(
        iban=DEGIRO_IBAN,
        defaults={
            "name": "Degiro",
            "bank": "flatexDEGIRO Bank",
            "scope": Account.Scope.PERSONAL,
            "role": Account.Role.PERSONAL,
            "kind": Account.Kind.BROKERAGE,
        },
    )
    investment_cat, _ = Category.objects.get_or_create(name="Investment", defaults={"kind": Category.Kind.INVESTMENT})
    # Dividends and Flatex interest land in a dedicated income category so the
    # cashflow and income dashboards reflect what the broker has actually paid
    # the user across the period.
    investment_income_cat, _ = Category.objects.get_or_create(
        name="Investment income", defaults={"kind": Category.Kind.INCOME}
    )
    # Map the parser's movement kind onto the right category
    category_by_kind = {
        "deposit": investment_cat,
        "withdrawal": investment_cat,
        "dividend": investment_income_cat,
        "interest": investment_income_cat,
    }

    created = 0
    skipped = 0
    for movement in parsed.movements:
        key = Transaction.build_dedupe_key(
            account.id, movement.date, movement.description, movement.amount, movement.balance
        )
        _, was_created = Transaction.objects.get_or_create(
            dedupe_key=key,
            defaults={
                "account": account,
                "date": movement.date,
                "description": movement.description,
                "amount": movement.amount,
                "balance": movement.balance,
                "category": category_by_kind[movement.kind],
            },
        )
        if was_created:
            created += 1
        else:
            skipped += 1

    return {
        "account": account,
        "movements": len(parsed.movements),
        "created": created,
        "skipped": skipped,
        "source_file": source_file,
    }


def _promote_household_accounts():
    """
    Tag any personal-scope account with Mortgage transactions as the household.

    Idempotent: accounts already marked as HOUSE are left alone, and accounts
    without a Mortgage movement keep their existing role.

    Args:
        None

    Returns:
        int: The number of accounts whose role was promoted
    """

    mortgage = Category.objects.filter(name="Mortgage").first()
    if mortgage is None:
        return 0

    promoted = 0
    candidates = Account.objects.filter(scope=Account.Scope.PERSONAL).exclude(role=Account.Role.HOUSE)
    for account in candidates:
        if account.transactions.filter(category=mortgage).exists():
            account.role = Account.Role.HOUSE
            account.save(update_fields=["role"])
            promoted += 1
    return promoted


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


@transaction.atomic
def apply_seed(data):
    """
    Apply a seed payload to the Category, CategoryRule and IgnoreRule tables.

    Shared between the seed_finance management command and the /api/seed/
    endpoint so the CLI and the browser write through the same code path.
    Idempotent: existing categories are reused; rules and ignore patterns
    are upserted on their natural keys so re-applying the same payload is
    a no-op.

    Args:
        data (dict): Parsed JSON with optional "categories", "rules" and
            "ignore" arrays. Shape mirrors seed_rules.json.

    Returns:
        dict: Summary counts {categories, rules_created, rules_updated,
        ignore_created, ignore_updated}

    Raises:
        Category.DoesNotExist: When a rule names a category that wasn't
            seeded and doesn't already exist
        KeyError: When a rule or ignore entry is missing a required field
    """

    categories = {}
    for entry in data.get("categories", []):
        category, _ = Category.objects.get_or_create(
            name=entry["name"], defaults={"kind": entry.get("kind", Category.Kind.EXPENSE)}
        )
        categories[entry["name"]] = category

    rules_created = 0
    rules_updated = 0
    for entry in data.get("rules", []):
        category = categories.get(entry["category"]) or Category.objects.get(name=entry["category"])
        # Treat (match_text, sign, scope, effective_from) as the natural key.
        # Editing the category for an existing match in the seed file then
        # updates the rule in place instead of inserting a duplicate that
        # would compete with the old one at classify time.
        _, was_created = CategoryRule.objects.update_or_create(
            match_text=entry["match_text"],
            sign=entry.get("sign", CategoryRule.Sign.ANY),
            scope=entry.get("scope", ""),
            effective_from=entry.get("effective_from") or None,
            defaults={
                "category": category,
                "priority": entry.get("priority", 100),
            },
        )
        if was_created:
            rules_created += 1
        else:
            rules_updated += 1

    # Importer ignore patterns (match_text is the natural key). The note is
    # advisory; we never drop patterns the user added through other channels.
    ignore_created = 0
    ignore_updated = 0
    for entry in data.get("ignore", []):
        _, was_created = IgnoreRule.objects.update_or_create(
            match_text=entry["match_text"],
            defaults={"note": entry.get("note", "")},
        )
        if was_created:
            ignore_created += 1
        else:
            ignore_updated += 1

    return {
        "categories": len(categories),
        "rules_created": rules_created,
        "rules_updated": rules_updated,
        "ignore_created": ignore_created,
        "ignore_updated": ignore_updated,
    }


def dump_seed():
    """
    Snapshot the current Category, CategoryRule and IgnoreRule rows as the
    payload a seed file would carry.

    The shape mirrors seed_rules.json so the export can be re-applied via
    apply_seed without any transformation. Useful for backing up the
    current config or for downloading the live state from the dashboard.

    Args:
        None

    Returns:
        dict: {"categories": [...], "rules": [...], "ignore": [...]}
    """

    categories = [{"name": c.name, "kind": c.kind} for c in Category.objects.order_by("name")]
    rules = []
    for r in CategoryRule.objects.select_related("category").order_by("priority", "match_text"):
        entry = {
            "match_text": r.match_text,
            "sign": r.sign,
            "scope": r.scope,
            "category": r.category.name,
            "priority": r.priority,
        }
        if r.effective_from:
            entry["effective_from"] = r.effective_from.isoformat()
        rules.append(entry)
    ignore = [{"match_text": i.match_text, "note": i.note} for i in IgnoreRule.objects.order_by("match_text")]
    return {"categories": categories, "rules": rules, "ignore": ignore}
