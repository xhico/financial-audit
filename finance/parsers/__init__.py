# Author: xhico
# Date: May 27, 2026
"""
Bank-statement parsers.

Each parser turns the text extracted from a statement PDF into a normalised
ParsedStatement, independent of the database, so it can be unit tested without
Django. The import layer maps the result onto the ORM models.
"""

from finance.parsers.base import (
    ParsedAccount,
    ParsedSnapshot,
    ParsedStatement,
    ParsedTransaction,
    detect_bank,
    extract_text,
    parse,
)

__all__ = [
    "ParsedAccount",
    "ParsedSnapshot",
    "ParsedStatement",
    "ParsedTransaction",
    "detect_bank",
    "extract_text",
    "parse",
]
