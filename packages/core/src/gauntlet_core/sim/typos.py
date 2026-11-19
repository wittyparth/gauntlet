"""Deterministic typo injection for low-literacy personas."""

from __future__ import annotations

import re
from collections.abc import Callable

__all__ = ["apply_typos"]

_TOKEN = re.compile(r"(\s+)")


def _mutate(word: str, rng: Callable[[], float]) -> str:
    op = int(rng() * 3)
    i = int(rng() * (len(word) - 1))
    if op == 0 and word[i] != word[i + 1]:  # transpose adjacent
        return word[:i] + word[i + 1] + word[i] + word[i + 2 :]
    if op == 1:  # drop a letter
        return word[:i] + word[i + 1 :]
    return word[: i + 1] + word[i] + word[i + 1 :]  # double a letter


def apply_typos(text: str, rate: float, rng: Callable[[], float]) -> str:
    """Mutate each plain word (4+ letters, letters only) with probability `rate`. Tokens with
    digits, `@`, `#` or punctuation (order ids, emails) are never touched. Each mutated word
    changes length by at most one character."""
    if rate <= 0:
        return text
    out: list[str] = []
    for tok in _TOKEN.split(text):
        if len(tok) >= 4 and tok.isalpha() and rng() < rate:
            tok = _mutate(tok, rng)
        out.append(tok)
    return "".join(out)
