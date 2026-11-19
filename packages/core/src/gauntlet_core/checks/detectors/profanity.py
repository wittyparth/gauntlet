"""Profanity: whole-word match against the vendored LDNOOBW list with leetspeak handling."""

from __future__ import annotations

import re
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

from .types import Hit

_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "@": "a", "$": "s"})
_DATA = Path(__file__).parent / "data" / "profanity_en.txt"


def _squash(s: str, keep: int) -> tuple[str, list[int]]:
    """Collapse runs of one repeated letter to `keep`; returns text and original indices."""
    out: list[str] = []
    idx: list[int] = []
    run = 0
    for i, ch in enumerate(s):
        run = run + 1 if out and out[-1] == ch and ch.isalpha() else 1
        if run <= keep:
            out.append(ch)
            idx.append(i)
    return "".join(out), idx


def _norm_word(w: str, keep: int) -> str:
    return _squash(w.lower().translate(_LEET), keep)[0]


@lru_cache(maxsize=1)
def _base_words() -> tuple[str, ...]:
    return tuple(
        w.strip().lower() for w in _DATA.read_text(encoding="utf-8").splitlines() if w.strip()
    )


@lru_cache(maxsize=32)
def _compile(words: tuple[str, ...], keep: int) -> re.Pattern[str]:
    normed = sorted({_norm_word(w, keep) for w in words if w}, key=len, reverse=True)
    alt = "|".join(re.escape(w) for w in normed)
    return re.compile(rf"(?<![a-z0-9])(?:{alt})(?![a-z0-9])")


def _mask(s: str) -> str:
    return s[0] + "*" * (len(s) - 1)


def detect_profanity(
    text: str, *, extra_words: Sequence[str] = (), allow: Sequence[str] = ()
) -> list[Hit]:
    words = (*_base_words(), *(w.lower() for w in extra_words))
    allowed = {_norm_word(w, 2) for w in allow}
    spans: dict[tuple[int, int], None] = {}
    lowered = text.lower().translate(_LEET)
    passes = [2]
    if re.search(r"([a-z])\1\1", lowered):
        passes.append(1)
    for keep in passes:
        norm, idx = _squash(lowered, keep)
        for m in _compile(words, keep).finditer(norm):
            if not m.group():
                continue
            start, end = idx[m.start()], idx[m.end() - 1] + 1
            if _norm_word(text[start:end], 2) in allowed or m.group() in allowed:
                continue
            spans[(start, end)] = None
    hits: list[Hit] = []
    last_end = -1
    for start, end in sorted(spans):
        if start < last_end:
            continue
        last_end = end
        hits.append(Hit("profanity", _mask(text[start:end]), None, start, end))
    return hits
