# Author: xhico
# Date: May 29, 2026
"""Data migration: retag the Degiro Cash Account as a brokerage account."""

from django.db import migrations


def forwards(apps, schema_editor):
    """
    Set kind=brokerage on the Degiro Cash Account if it exists.

    Args:
        apps: Historical models registry
        schema_editor: Database schema editor

    Returns:
        None
    """

    Account = apps.get_model("finance", "Account")
    Account.objects.filter(iban="DEGIROCASHACCOUNT").update(kind="brokerage")


def backwards(apps, schema_editor):
    """
    Revert the Degiro Cash Account kind to term deposit.

    Args:
        apps: Historical models registry
        schema_editor: Database schema editor

    Returns:
        None
    """

    Account = apps.get_model("finance", "Account")
    Account.objects.filter(iban="DEGIROCASHACCOUNT").update(kind="term")


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0007_alter_account_kind"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
