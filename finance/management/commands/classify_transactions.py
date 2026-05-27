# Author: xhico
# Date: May 27, 2026
"""Management command to (re)classify all transactions against the rules."""

from django.core.management.base import BaseCommand

from finance.services import classify_transactions


class Command(BaseCommand):
    """
    Apply the category rules to every transaction.

    - Useful after editing rules, since import only classifies new movements
    """

    help = "Re-run category classification across all transactions."

    def handle(self, *args, **options):
        """
        Classify all transactions and report how many changed.

        Args:
            args: Unused positional arguments
            options (dict): Parsed command options

        Returns:
            None
        """

        updated = classify_transactions()
        self.stdout.write(self.style.SUCCESS(f"Reclassified {updated} transactions."))
