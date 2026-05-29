# Author: xhico
# Date: May 27, 2026
"""Admin registrations for the finance app."""

from django.contrib import admin

from finance.models import Account, Category, CategoryRule, StatementImport, Transaction


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    """
    Admin for bank accounts.

    - Lists the account with its scope, bank and kind
    - Allows filtering by scope and kind
    """

    list_display = ("name", "bank", "scope", "role", "kind", "iban", "currency")
    list_filter = ("scope", "role", "kind", "bank")
    search_fields = ("name", "iban", "bank")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """
    Admin for transaction categories.

    - Lists the category with its kind and parent
    - Allows filtering by kind
    """

    list_display = ("name", "kind", "parent")
    list_filter = ("kind",)
    search_fields = ("name",)


@admin.register(CategoryRule)
class CategoryRuleAdmin(admin.ModelAdmin):
    """
    Admin for category rules.

    - Lists the match text, sign, scope, category and priority
    - Ordered so the highest-priority rules show first
    """

    list_display = ("match_text", "sign", "scope", "effective_from", "category", "priority")
    list_filter = ("sign", "scope", "category")
    search_fields = ("match_text",)


@admin.register(StatementImport)
class StatementImportAdmin(admin.ModelAdmin):
    """
    Admin for imported statements.

    - Lists the bank, scope and period for each import
    - Allows filtering by bank and scope
    """

    list_display = ("bank", "scope", "statement_number", "period_start", "period_end", "imported_at")
    list_filter = ("bank", "scope")
    date_hierarchy = "period_end"


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    """
    Admin for transactions.

    - Lists the date, account, amount, balance and category
    - Allows filtering by account, scope and category
    """

    list_display = ("date", "account", "amount", "balance", "category", "description")
    list_filter = ("account__scope", "account", "category")
    search_fields = ("description",)
    date_hierarchy = "date"
    autocomplete_fields = ("category",)
