# Author: xhico
# Date: May 27, 2026
"""
Parser for Degiro annual reports ("Relatório Anual").

Each annual report carries a "Conta Caixa flatex" section listing the year's
total deposits from the user's external bank account into Degiro and the
total withdrawals back out. Those figures are the authoritative record of
what actually reached the broker for the year — bank statements often miss
some of the movements when the user funds Degiro via Revolut or other routes.
"""

import re
from dataclasses import dataclass
from decimal import Decimal

# A Portuguese-formatted money value, optionally with space thousands separators
DEGIRO_MONEY_RE = re.compile(r"\d{1,3}(?:[ .]\d{3})*,\d{2}")

YEAR_RE = re.compile(r"Relat[óo]rio Anual\s+(\d{4})")
DEPOSITS_RE = re.compile(r"Valor total de dep[óo]sitos\*?\s+(" + DEGIRO_MONEY_RE.pattern + r")\s*EUR")
WITHDRAWALS_RE = re.compile(r"Valor total de levantamentos\*?\s+(" + DEGIRO_MONEY_RE.pattern + r")\s*EUR")


def _parse_amount(token):
    """
    Parse a Portuguese-formatted Degiro amount into a Decimal.

    Args:
        token (str): The money string, e.g. "4 223,83" or "100,00"

    Returns:
        Decimal: The parsed value
    """

    return Decimal(token.strip().replace(" ", "").replace(".", "").replace(",", "."))


@dataclass
class ParsedDegiroReport:
    """
    The headline figures extracted from a Degiro Relatório Anual.

    - Captures the deposits and withdrawals on the Conta Caixa flatex
    - Carries the reporting year, used as the synthetic year-end date
    """

    year: int
    deposits: Decimal
    withdrawals: Decimal


def parse(text):
    """
    Parse a Degiro annual report's text into its headline figures.

    Args:
        text (str): The extracted report text

    Returns:
        ParsedDegiroReport: The year, deposits and withdrawals

    Raises:
        ValueError: When the year, deposits or withdrawals cannot be found
    """

    m_year = YEAR_RE.search(text)
    m_dep = DEPOSITS_RE.search(text)
    m_with = WITHDRAWALS_RE.search(text)
    if not (m_year and m_dep and m_with):
        raise ValueError("Could not find year, deposits and withdrawals in Degiro report")
    return ParsedDegiroReport(
        year=int(m_year.group(1)),
        deposits=_parse_amount(m_dep.group(1)),
        withdrawals=_parse_amount(m_with.group(1)),
    )
