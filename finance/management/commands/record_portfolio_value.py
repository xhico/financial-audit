# Author: xhico
# Date: May 29, 2026
"""Management command to record a manual brokerage portfolio snapshot."""

from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError

from finance.models import Account, PortfolioSnapshot


class Command(BaseCommand):
    """
    Record the market value of a brokerage account on a given date.

    - One row per (account, date); re-running updates the value in place
    - Used to drive the Investments page's valuation and unrealised-gain tiles
    """

    help = "Record a manual portfolio-value snapshot for a brokerage account."

    def add_arguments(self, parser):
        """
        Declare the command-line arguments.

        Args:
            parser (argparse.ArgumentParser): The command parser

        Returns:
            None
        """

        parser.add_argument("iban", help="IBAN of the brokerage account")
        parser.add_argument("as_of", help="Snapshot date in YYYY-MM-DD format")
        parser.add_argument("market_value", help="Total account value at as_of, in EUR")
        parser.add_argument("--note", default="", help="Optional note attached to the snapshot")

    def handle(self, *args, **options):
        """
        Validate inputs and upsert the snapshot.

        Args:
            args: Unused positional arguments
            options (dict): Parsed command options

        Returns:
            None

        Raises:
            CommandError: When the account is missing or the inputs fail to parse
        """

        try:
            account = Account.objects.get(iban=options["iban"])
        except Account.DoesNotExist as exc:
            raise CommandError(f"No account with IBAN {options['iban']!r}") from exc

        try:
            as_of = datetime.strptime(options["as_of"], "%Y-%m-%d").date()
        except ValueError as exc:
            raise CommandError(f"Bad date {options['as_of']!r}, expected YYYY-MM-DD") from exc

        try:
            market_value = Decimal(options["market_value"])
        except InvalidOperation as exc:
            raise CommandError(f"Bad market value {options['market_value']!r}") from exc

        snapshot, created = PortfolioSnapshot.objects.update_or_create(
            account=account,
            as_of=as_of,
            defaults={"market_value": market_value, "note": options["note"]},
        )

        verb = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(f"{verb} portfolio snapshot for {account.name} on {as_of}: {snapshot.market_value} EUR")
        )
