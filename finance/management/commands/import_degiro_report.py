# Author: xhico
# Date: May 27, 2026
"""Management command to import one or more Degiro annual reports."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from finance.parsers import extract_text
from finance.services import import_degiro_report


class Command(BaseCommand):
    """
    Import Degiro Relatório Anual PDFs into the finance ledger.

    - Reads the authoritative annual deposit / withdrawal totals
    - Books one synthetic Investment-categorised transaction per year on a
      shared Degiro Cash Account
    """

    help = "Import one or more Degiro annual report PDFs into the finance ledger."

    def add_arguments(self, parser):
        """
        Declare the command-line arguments.

        Args:
            parser (argparse.ArgumentParser): The command parser

        Returns:
            None
        """

        # One or more PDF paths to the Degiro Relatório Anual files
        parser.add_argument("paths", nargs="+", help="Paths to Degiro annual report PDFs")

    def handle(self, *args, **options):
        """
        Import each given report and report the per-year flows.

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
            result = import_degiro_report(text, source_file=path.name)

            self.stdout.write(
                self.style.SUCCESS(
                    f"{path.name}: {result['year']} — "
                    f"+€{result['deposits']} deposits / €{result['withdrawals']} withdrawals "
                    f"(net €{result['net']}) — "
                    f"{result['created']} new, {result['skipped']} existing"
                )
            )
