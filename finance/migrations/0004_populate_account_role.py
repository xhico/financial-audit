# Author: xhico
# Date: May 27, 2026
"""Populate Account.role from scope and Mortgage transactions."""

from django.db import migrations


def populate_roles(apps, schema_editor):
    """
    Seed Account.role from existing data.

    A personal account that already has any "Mortgage" category transaction is
    tagged as the household; the rest fall back to the role implied by scope.

    Args:
        apps (StateApps): Historical app registry from the migration framework
        schema_editor: The database schema editor (unused)

    Returns:
        None
    """

    Account = apps.get_model("finance", "Account")
    Category = apps.get_model("finance", "Category")

    # Look up the Mortgage category if the user has seeded it
    mortgage = Category.objects.filter(name="Mortgage").first()
    mortgage_id = mortgage.id if mortgage else None

    for account in Account.objects.all():
        if account.scope == "business":
            account.role = "business"
        elif mortgage_id is not None and account.transactions.filter(category_id=mortgage_id).exists():
            account.role = "house"
        else:
            account.role = "personal"
        account.save(update_fields=["role"])


def noop(apps, schema_editor):
    """
    Reverse migration is a no-op since the column is dropped on rollback.

    Args:
        apps (StateApps): Unused
        schema_editor: Unused

    Returns:
        None
    """


class Migration(migrations.Migration):
    """Seed Account.role values for existing accounts."""

    dependencies = [
        ("finance", "0003_account_role"),
    ]

    operations = [
        migrations.RunPython(populate_roles, noop),
    ]
