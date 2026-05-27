# Author: xhico
# Date: May 27, 2026
"""Management command to import one or more bank-statement PDFs."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from finance.parsers import extract_text
from finance.services import import_statement


class Command(BaseCommand):
    """
    Import bank-statement PDFs into accounts and transactions.

    - Accepts one or more PDF paths
    - Detects the bank automatically and dedupes on re-import
    """

    help = "Import one or more bank-statement PDFs into the finance ledger."

    def add_arguments(self, parser):
        """
        Declare the command-line arguments.

        Args:
            parser (argparse.ArgumentParser): The command parser

        Returns:
            None
        """

        # One or more PDF file paths to import
        parser.add_argument("paths", nargs="+", help="Paths to statement PDF files")

    def handle(self, *args, **options):
        """
        Import each given PDF and report the counts.

        Args:
            args: Unused positional arguments
            options (dict): Parsed command options including the paths

        Returns:
            None

        Raises:
            CommandError: When a path does not exist
        """

        for raw_path in options["paths"]:
            path = Path(raw_path)
            if not path.is_file():
                raise CommandError(f"File not found: {path}")

            text = extract_text(str(path))
            result = import_statement(text, source_file=path.name)

            ibans = ", ".join(a.iban for a in result.accounts)
            self.stdout.write(
                self.style.SUCCESS(
                    f"{path.name}: +{result.created} new, {result.skipped} existing "
                    f"({result.statement}; accounts: {ibans})"
                )
            )
