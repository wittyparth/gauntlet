"""`split:<n>`: spread the payload over n turns. Placeholders are atomic."""

from __future__ import annotations

import random
import re

from gauntlet_core.llm import Gateway
from gauntlet_core.schema import Attack
from gauntlet_core.security.placeholders import PLACEHOLDER_RE

from .base import derive

__all__ = ["SUFFIX", "SplitMutation", "split_parts"]

SUFFIX = " (part {i} of {n}; more follows)"
_SENT = re.compile(r"(?<=[.!?])\s+")
_MASK = ""


def _mask(text: str) -> tuple[str, list[str]]:
    held: list[str] = []

    def hold(m: re.Match[str]) -> str:
        held.append(m.group(0))
        return _MASK

    return PLACEHOLDER_RE.sub(hold, text), held


def _unmask(text: str, held: list[str]) -> str:
    it = iter(held)
    return re.sub(_MASK, lambda _m: next(it), text)


def _split_longest(parts: list[str]) -> bool:
    """Split the longest part at the whitespace nearest its middle. False if impossible."""
    i = max(range(len(parts)), key=lambda k: len(parts[k]))
    text = parts[i]
    mid = len(text) // 2
    spaces = [m.start() for m in re.finditer(r"\s", text) if 0 < m.start() < len(text) - 1]
    if not spaces:
        return False
    cut = min(spaces, key=lambda s: abs(s - mid))
    parts[i : i + 1] = [text[:cut].rstrip(), text[cut:].lstrip()]
    return True


def split_parts(text: str, n: int) -> list[str] | None:
    """n parts (fewer only when the text cannot be split further); None for a single
    sentence."""
    masked, held = _mask(text.strip())
    sentences = [s for s in _SENT.split(masked) if s.strip()]
    if len(sentences) < 2:
        return None
    parts = sentences
    while len(parts) > n:  # merge the shortest adjacent pair
        i = min(range(len(parts) - 1), key=lambda k: len(parts[k]) + len(parts[k + 1]))
        parts[i : i + 2] = [parts[i] + " " + parts[i + 1]]
    while len(parts) < n and _split_longest(parts):
        pass
    return [_unmask(p, held) for p in parts]


class SplitMutation:
    def __init__(self, n: int) -> None:
        if not 2 <= n <= 4:
            raise ValueError("split takes 2..4")
        self.n = n
        self.name = f"split:{n}"

    async def apply(
        self, attack: Attack, *, rng: random.Random, gateway: Gateway | None
    ) -> list[Attack]:
        if not isinstance(attack.payload, str):
            return []
        parts = split_parts(attack.payload, self.n)
        if parts is None:
            return []  # a single sentence yields no variant
        total = len(parts)
        turns = [
            p + SUFFIX.format(i=i, n=total) if i < total else p for i, p in enumerate(parts, 1)
        ]
        a = derive(attack, self.name, turns, extra_requires=("multi_turn",))
        return [a] if a else []
