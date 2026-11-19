"""Near-duplicate detection for generated scenarios: normalised token Jaccard."""

from __future__ import annotations

import re
from collections.abc import Iterable

__all__ = ["THRESHOLD", "is_duplicate", "jaccard", "tokens"]

THRESHOLD = 0.7
_WORD = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> frozenset[str]:
    return frozenset(_WORD.findall(text.lower()))


def jaccard(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def is_duplicate(text: str, others: Iterable[str], threshold: float = THRESHOLD) -> bool:
    return any(jaccard(text, o) > threshold for o in others)
