---
name: code-style
description: Python file conventions for this project — author/date signature, docstrings, inline comments, and README updates. Apply whenever creating or editing Python files.
---

# Python code style

Apply these rules to every Python file you create or edit in this project.

## 1. File header

Every `.py` file begins with a 2-line header (use the real current date in
`Mon DD, YYYY` format):

```python
# Author: xhico
# Date: May 27, 2026
```

For `manage.py`, the shebang stays on line 1 and the header goes on lines 2–3.

## 2. Class docstrings

Triple-quoted. A one-sentence description, a blank line, then a bullet list of
responsibilities or fields.

```python
class Invoice:
    """
    Represent a single customer invoice.

    - Holds line items and totals
    - Computes tax based on the billing region
    """
```

## 3. Method / function docstrings

Triple-quoted. A description, then `Args:` (type in parentheses), `Returns:`,
and optionally `Process:` and `Raises:`.

```python
def total(self, region):
    """
    Compute the gross total for a region.

    Args:
        region (str): ISO billing region code

    Returns:
        Decimal: Gross total including tax
    """
```

## 4. Inline comments

A single `#` followed by one space, placed on the line **before** the code it
describes — never at the end of a line of code.

## 5. DRF serializer / form docstrings

A description followed by a `Rules:` section listing the validation rules.

## 6. README updates

Update the app-level README and the top-level README on any module change.

## 7. British English

Use British spelling everywhere (normalise, serialise, behaviour, colour).

## 8. No multiple spaces

Do not use multiple spaces inside docstrings or comments to align text.

## 9. No backticks

Do not use backticks in docstrings or comments — use single or double quotes.
