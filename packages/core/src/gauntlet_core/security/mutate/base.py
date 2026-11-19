"""Mutation protocol and helpers. Placeholders are inviolable: mutations only transform the
text between placeholders, and `derive` drops any variant whose placeholder multiset changed."""

from __future__ import annotations

import hashlib
import random
from collections import Counter
from collections.abc import Callable
from typing import Protocol

from gauntlet_core.llm import Gateway
from gauntlet_core.schema import Attack
from gauntlet_core.security.placeholders import PLACEHOLDER_RE, extract_placeholders

__all__ = [
    "Mutation",
    "add_requires",
    "derive",
    "derive_id",
    "map_segments",
    "same_placeholders",
]


class Mutation(Protocol):
    name: str

    async def apply(
        self, attack: Attack, *, rng: random.Random, gateway: Gateway | None
    ) -> list[Attack]: ...


def map_segments(text: str, fn: Callable[[str], str]) -> str:
    """Apply `fn` to each stretch of text between placeholders; placeholders stay verbatim."""
    out: list[str] = []
    pos = 0
    for m in PLACEHOLDER_RE.finditer(text):
        out.append(fn(text[pos : m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(fn(text[pos:]))
    return "".join(out)


def same_placeholders(a: str | list[str], b: str | list[str]) -> bool:
    def bag(p: str | list[str]) -> Counter[str]:
        return Counter(
            x for t in ([p] if isinstance(p, str) else p) for x in extract_placeholders(t)
        )

    return bag(a) == bag(b)


def derive_id(orig_id: str, names: list[str]) -> str:
    """`<orig>_m<hash of the chain>`. The plan's `<orig>~a+b` form cannot satisfy the library id
    rule (`^atk_[a-z0-9_]{3,40}$`), so the readable chain lives in `technique` instead."""
    suffix = "+".join(names)
    tag = hashlib.sha256(suffix.encode()).hexdigest()[:8]
    new = f"{orig_id}_m{tag}"
    if len(new) - len("atk_") > 40:
        new = f"atk_m{hashlib.sha256((orig_id + '~' + suffix).encode()).hexdigest()[:16]}"
    return new


def add_requires(requires: list[str], *extra: str) -> list[str]:
    return [*requires, *(e for e in extra if e not in requires)]


def derive(
    orig: Attack,
    spec: str,
    payload: str | list[str],
    *,
    extra_requires: tuple[str, ...] = (),
    **overrides: object,
) -> Attack | None:
    """The mutated attack, or None when the placeholder multiset would change."""
    if not same_placeholders(orig.payload, payload):
        return None
    return orig.model_copy(
        update={
            "id": derive_id(orig.id, [spec]),
            "technique": f"{orig.technique}+{spec}",
            "payload": payload,
            "requires": add_requires(list(orig.requires), *extra_requires),
            **overrides,
        }
    )
