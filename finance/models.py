# Author: xhico
# Date: May 27, 2026
"""
Domain models for the finance app.

These mirror the information previously kept in the spreadsheet ledger: bank
accounts (personal/household and business), the statements imported each month
and the individual transactions, classified into categories for the dashboards.
"""

import hashlib

from django.db import models


class Account(models.Model):
    """
    A bank account whose statements feed the ledger.

    - Identifies the owning scope (personal/household versus business)
    - Carries the bank and IBAN used to match imported statements
    - Groups the transactions imported for it
    """

    class Scope(models.TextChoices):
        PERSONAL = "personal", "Personal / household"
        BUSINESS = "business", "Business"

    class Kind(models.TextChoices):
        CURRENT = "current", "Current"
        SAVINGS = "savings", "Savings"
        TERM = "term", "Term deposit"
        CREDIT = "credit", "Credit"
        # An investment / brokerage account (e.g. Degiro). Excluded from the
        # Accounts list and the role-based net-worth buckets, because the
        # stored balance only reflects uninvested cash at the broker, not
        # the portfolio value.
        BROKERAGE = "brokerage", "Brokerage"

    class Role(models.TextChoices):
        HOUSE = "house", "Household (holds the mortgage)"
        PERSONAL = "personal", "Personal"
        BUSINESS = "business", "Business"

    name = models.CharField(max_length=120)
    bank = models.CharField(max_length=120)
    # Normalised IBAN (no spaces) used to match transactions to this account
    iban = models.CharField(max_length=34, unique=True)
    scope = models.CharField(max_length=10, choices=Scope.choices)
    # Finer breakdown for net-worth views; the migration seeds this from scope
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.PERSONAL)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.CURRENT)
    currency = models.CharField(max_length=3, default="EUR")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scope", "name"]

    def __str__(self):
        """
        Return a readable label for the account.

        Args:
            None

        Returns:
            str: The account name with its bank
        """

        return f"{self.name} ({self.bank})"


class Category(models.Model):
    """
    A label for classifying transactions on the dashboards.

    - Groups income and spend into meaningful buckets (mortgage, utilities…)
    - Supports an optional parent for a shallow hierarchy
    - Carries a kind so dashboards can separate income from expense
    """

    class Kind(models.TextChoices):
        INCOME = "income", "Income"
        EXPENSE = "expense", "Expense"
        TRANSFER = "transfer", "Transfer"
        INVESTMENT = "investment", "Investment"
        TAX = "tax", "Tax"
        OTHER = "other", "Other"

    name = models.CharField(max_length=80, unique=True)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.EXPENSE)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["kind", "name"]

    def __str__(self):
        """
        Return the category name.

        Args:
            None

        Returns:
            str: The category name
        """

        return self.name


class CategoryRule(models.Model):
    """
    A rule that assigns a category to matching transactions.

    - Matches a case-insensitive substring against the description
    - Optionally restricts by movement sign and account scope
    - Lower priority values are applied first; the first match wins
    """

    class Sign(models.TextChoices):
        ANY = "any", "Any"
        CREDIT = "credit", "Credit (money in)"
        DEBIT = "debit", "Debit (money out)"

    match_text = models.CharField(max_length=120)
    sign = models.CharField(max_length=6, choices=Sign.choices, default=Sign.ANY)
    # Blank scope matches any account scope
    scope = models.CharField(max_length=10, choices=Account.Scope.choices, blank=True)
    # Only match transactions on or after this date when set; lets the same
    # description map to different categories before and after a cut-off
    effective_from = models.DateField(null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="rules")
    priority = models.IntegerField(default=100)

    class Meta:
        ordering = ["priority", "id"]

    def __str__(self):
        """
        Return a readable label for the rule.

        Args:
            None

        Returns:
            str: The match text and the category it assigns
        """

        return f"{self.match_text!r} -> {self.category}"

    def matches(self, txn):
        """
        Decide whether this rule applies to a transaction.

        Args:
            txn (Transaction): The transaction to test

        Returns:
            bool: True when the description, sign and scope all match
        """

        if self.match_text.lower() not in txn.description.lower():
            return False
        if self.sign == self.Sign.CREDIT and txn.amount <= 0:
            return False
        if self.sign == self.Sign.DEBIT and txn.amount >= 0:
            return False
        if self.scope and txn.account.scope != self.scope:
            return False
        if self.effective_from and txn.date < self.effective_from:
            return False
        return True


class IgnoreRule(models.Model):
    """
    A pattern that causes the statement importer to skip matching transactions.

    - Lets you drop noisy rows (e.g. internal-transfer mirrors of broker deposits)
    - Matched case-insensitively as a substring of the transaction description
    """

    match_text = models.CharField(max_length=120, unique=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["match_text"]

    def __str__(self):
        """
        Return a readable label for the rule.

        Args:
            None

        Returns:
            str: A short description of the pattern
        """

        return f"Skip {self.match_text!r}"


class StatementImport(models.Model):
    """
    A single imported bank-statement PDF.

    - Records provenance for the transactions it created
    - Holds the statement period and source bank
    - Lets a month be re-imported safely, since transactions dedupe on import
    """

    class Bank(models.TextChoices):
        CREDITO_AGRICOLA = "credito_agricola", "Crédito Agrícola"
        CGD = "cgd", "Caixa Geral de Depósitos"

    bank = models.CharField(max_length=20, choices=Bank.choices)
    scope = models.CharField(max_length=10, choices=Account.Scope.choices)
    statement_number = models.CharField(max_length=20, blank=True)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    # Original filename the import came from, kept for traceability
    source_file = models.CharField(max_length=255, blank=True)
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-period_end", "-imported_at"]

    def __str__(self):
        """
        Return a readable label for the import.

        Args:
            None

        Returns:
            str: The bank and statement period
        """

        return f"{self.get_bank_display()} {self.period_start} to {self.period_end}"


class BalanceSnapshot(models.Model):
    """
    End-of-period balances taken from a statement summary.

    - Captures the headline figures the CGD global statement prints each month
    - Feeds the savings and net-worth trends without summing transactions
    - Tied to the import that produced it
    """

    statement = models.ForeignKey(StatementImport, on_delete=models.CASCADE, related_name="snapshots")
    as_of = models.DateField()
    # Total across current ("À Ordem") accounts
    current_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    # Total across savings / term deposits ("A Prazo / Poupança")
    savings_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    # Financial instruments held at the bank ("Instrumentos financeiros")
    investments_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    # Outstanding mortgage debt ("Crédito Imobiliário")
    mortgage_balance = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["-as_of"]

    def __str__(self):
        """
        Return a readable label for the snapshot.

        Args:
            None

        Returns:
            str: The snapshot date
        """

        return f"Balances at {self.as_of}"


class PortfolioSnapshot(models.Model):
    """
    Manually recorded market value of a brokerage account at a point in time.

    - One row per (account, as_of) date
    - Combined with the Investment-category transactions to derive an
      unrealised gain on the Investments page
    - Entered by the user once a month when refreshing the dashboard
    """

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="portfolio_snapshots")
    as_of = models.DateField()
    # The figure Degiro (or any other broker) prints as the account's total
    # value, in EUR. Includes positions and any uninvested cash.
    market_value = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-as_of"]
        constraints = [
            models.UniqueConstraint(fields=["account", "as_of"], name="unique_portfolio_snapshot"),
        ]

    def __str__(self):
        """
        Return a readable label for the snapshot.

        Args:
            None

        Returns:
            str: The account name and snapshot date
        """

        return f"{self.account.name} @ {self.as_of}: {self.market_value}"


class Transaction(models.Model):
    """
    A single posted movement on an account.

    - Stores the signed amount (negative is a debit) and the resulting balance
    - Links to the import it came from and the account it belongs to
    - Carries an optional category used by the dashboards
    """

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="transactions")
    statement = models.ForeignKey(
        StatementImport,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
    )
    # Posting date (Data Mov.) and the bank value date (Data Valor)
    date = models.DateField()
    value_date = models.DateField(null=True, blank=True)
    description = models.TextField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    balance = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    category = models.ForeignKey(
        Category,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
    )
    # Stable hash of the natural key, so re-importing a month is idempotent
    dedupe_key = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "id"]
        indexes = [
            models.Index(fields=["account", "date"]),
        ]

    def __str__(self):
        """
        Return a readable label for the transaction.

        Args:
            None

        Returns:
            str: The date, amount and a short description
        """

        return f"{self.date} {self.amount} {self.description[:40]}"

    def save(self, *args, **kwargs):
        """
        Populate the dedupe key before saving.

        Args:
            args: Positional arguments forwarded to the base save
            kwargs: Keyword arguments forwarded to the base save

        Returns:
            None
        """

        # Derive the key from the natural fields when it is not already set
        if not self.dedupe_key:
            self.dedupe_key = self.build_dedupe_key(
                self.account_id, self.date, self.description, self.amount, self.balance
            )
        super().save(*args, **kwargs)

    @staticmethod
    def build_dedupe_key(account_id, date, description, amount, balance):
        """
        Build the stable hash that identifies a transaction.

        The running balance is part of the key so two otherwise-identical
        movements on the same day (which carry different balances) are kept,
        while a re-import of the same statement collapses onto the same row.

        Args:
            account_id (int): Owning account primary key
            date (datetime.date): Posting date
            description (str): Movement description
            amount (decimal.Decimal): Signed amount
            balance (decimal.Decimal | None): Resulting balance

        Returns:
            str: A 64-character hexadecimal SHA-256 digest
        """

        # Join the natural-key parts with a separator unlikely to appear in them
        raw = f"{account_id}|{date}|{description}|{amount}|{balance}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
