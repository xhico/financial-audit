# Author: xhico
# Date: May 27, 2026
"""Application configuration for the finance app."""

from django.apps import AppConfig


class FinanceConfig(AppConfig):
    """
    Configuration for the finance app.

    - Sets the default primary key field type
    - Names the app that holds accounts, statements and transactions
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "finance"
