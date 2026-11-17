"""Text normalisation shared by canary planting (world) and canary detection (checks).

Both sides must normalise identically, so the function lives with the contracts.
"""

from __future__ import annotations


def canary_normalize(text: str) -> str:
    """Case-fold and drop everything that is not a letter or digit.

    Planted canary variants are stored already normalised; detection normalises the
    haystack the same way and does a substring search.
    """
    return "".join(ch for ch in text.casefold() if ch.isalnum())
