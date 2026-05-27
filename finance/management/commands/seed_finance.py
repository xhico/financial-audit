# Author: xhico
# Date: May 27, 2026
"""Management command to seed categories and rules from a JSON file."""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from finance.models import Category, CategoryRule


def _resolve_path(given):
    """
    Decide which seed file to load.

    Prefers an explicit path, then a private seed_rules.json at the project
    root, and finally the committed seed_rules.example.json template.

    Args:
        given (str | None): A path passed on the command line, or None

    Returns:
        pathlib.Path: The seed file to load

    Raises:
        CommandError: When no seed file can be found
    """

    if given:
        path = Path(given)
        if not path.is_file():
            raise CommandError(f"Seed file not found: {path}")
        return path

    private = Path(settings.BASE_DIR) / "seed_rules.json"
    example = Path(settings.BASE_DIR) / "seed_rules.example.json"
    if private.is_file():
        return private
    if example.is_file():
        return example
    raise CommandError("No seed_rules.json or seed_rules.example.json found")


class Command(BaseCommand):
    """
    Seed finance categories and classification rules from a JSON file.

    - Keeps the user's real match strings out of the codebase
    - Idempotent: existing categories and rules are left untouched
    """

    help = "Create finance categories and rules from a JSON seed file."

    def add_arguments(self, parser):
        """
        Declare the command-line arguments.

        Args:
            parser (argparse.ArgumentParser): The command parser

        Returns:
            None
        """

        # Optional explicit path to a seed file
        parser.add_argument("--file", dest="file", default=None, help="Path to a seed JSON file")

    def handle(self, *args, **options):
        """
        Load the seed file and create its categories and rules.

        Args:
            args: Unused positional arguments
            options (dict): Parsed command options including the file path

        Returns:
            None
        """

        path = _resolve_path(options["file"])
        data = json.loads(path.read_text(encoding="utf-8"))

        categories = {}
        for entry in data.get("categories", []):
            category, _ = Category.objects.get_or_create(
                name=entry["name"], defaults={"kind": entry.get("kind", Category.Kind.EXPENSE)}
            )
            categories[entry["name"]] = category

        created = 0
        for entry in data.get("rules", []):
            category = categories.get(entry["category"]) or Category.objects.get(name=entry["category"])
            _, was_created = CategoryRule.objects.get_or_create(
                match_text=entry["match_text"],
                category=category,
                defaults={
                    "sign": entry.get("sign", CategoryRule.Sign.ANY),
                    "scope": entry.get("scope", ""),
                    "priority": entry.get("priority", 100),
                },
            )
            created += int(was_created)

        self.stdout.write(
            self.style.SUCCESS(f"Seeded {len(categories)} categories and {created} new rules from {path.name}.")
        )
