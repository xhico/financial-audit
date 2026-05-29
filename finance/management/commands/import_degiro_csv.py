# Author: xhico
# Date: May 29, 2026
"""Management command to import a Degiro Account.csv export."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from finance.services import import_degiro_csv


class Command(BaseCommand):
    """
    Import a Degiro cash-account CSV export.

    - Accepts one CSV path
    - Inserts one Investment transaction per real deposit / withdrawal
    """

    help = "Import a Degiro Account.csv as per-deposit Investment transactions."

    def add_arguments(self, parser):
        """
        Declare the command-line arguments.

        Args:
            parser (argparse.ArgumentParser): The command parser

        Returns:
            None
        """

        # Path to a Degiro Account.csv export
        parser.add_argument("path", help="Path to the Degiro Account.csv file")

    def handle(self, *args, **options):
        """
        Import the CSV and report the counts.

        Args:
            args: Unused positional arguments
            options (dict): Parsed command options including the path

        Returns:
            None

        Raises:
            CommandError: When the path does not exist
        """

        path = Path(options["path"])
        if not path.is_file():
            raise CommandError(f"File not found: {path}")

        text = path.read_text(encoding="utf-8")
        result = import_degiro_csv(text, source_file=path.name)

        self.stdout.write(
            self.style.SUCCESS(
                f"{path.name}: {result['movements']} cash movements parsed, "
                f"{result['created']} new, {result['skipped']} existing "
                f"(account: {result['account'].iban})"
            )
        )
