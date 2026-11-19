"""Attack mutation engine (P2-3)."""

from __future__ import annotations

import logging
import random
from collections.abc import Sequence
from pathlib import Path

from gauntlet_core.llm import Gateway
from gauntlet_core.schema import Attack

from .base import Mutation, derive_id, same_placeholders
from .cache import MutationCache
from .embed import EmbedMutation
from .encode import EncodeMutation
from .llm_ops import LlmMutation
from .split import SplitMutation
from .wrap import WrapMutation

__all__ = [
    "MAX_CHAIN",
    "Mutation",
    "apply_mutations",
    "parse_spec",
]

log = logging.getLogger(__name__)
MAX_CHAIN = 3


def parse_spec(spec: str, *, cache: MutationCache | None = None) -> Mutation:
    kind, _, arg = spec.partition(":")
    if kind == "encode":
        return EncodeMutation(arg)
    if kind == "wrap":
        return WrapMutation(arg)
    if kind == "split":
        return SplitMutation(int(arg))
    if kind == "embed":
        return EmbedMutation(arg)
    if kind == "paraphrase" and not arg:
        return LlmMutation("paraphrase", cache=cache)
    if kind == "translate":
        return LlmMutation("translate", arg, cache=cache)
    raise ValueError(f"unknown mutation spec {spec!r}")


def _payload_text(a: Attack) -> str:
    return a.payload if isinstance(a.payload, str) else "\n".join(a.payload)


async def _chain(
    attack: Attack, muts: list[Mutation], rng: random.Random, gateway: Gateway | None
) -> Attack | None:
    cur: Attack | None = attack
    names: list[str] = []
    for m in muts:
        if cur is None:
            return None
        out = await m.apply(cur, rng=rng, gateway=gateway)
        cur = out[0] if out else None
        names.append(m.name)
    if cur is None or len(muts) == 1:
        return cur
    # a chain is one derived attack named after the whole chain, not its intermediate ids
    technique = attack.technique + "".join(f"+{n}" for n in names)
    return cur.model_copy(update={"id": derive_id(attack.id, names), "technique": technique})


async def apply_mutations(
    attacks: Sequence[Attack],
    specs: Sequence[str | Sequence[str]],
    *,
    gateway: Gateway | None = None,
    seed: int = 0,
    cache_path: Path | None = None,
    max_variants_per_attack: int = 6,
) -> list[Attack]:
    """Variants of each attack, one per spec (a sequence is a chain, left to right, at most 3).
    Deterministic for a seed; duplicate payloads are dropped; at most
    `max_variants_per_attack` per original (specs in the given order)."""
    cache = MutationCache(cache_path)
    plans: list[list[Mutation]] = []
    for spec in specs:
        names = [spec] if isinstance(spec, str) else list(spec)
        if not 1 <= len(names) <= MAX_CHAIN:
            raise ValueError(f"a chain has 1..{MAX_CHAIN} mutations")
        plans.append([parse_spec(n, cache=cache) for n in names])
    out: list[Attack] = []
    for attack in attacks:
        rng = random.Random(f"{seed}:{attack.id}")
        seen = {_payload_text(attack)}
        variants: list[Attack] = []
        for plan in plans:
            if len(variants) >= max_variants_per_attack:
                break
            v = await _chain(attack, plan, rng, gateway)
            if (
                v is None
                or _payload_text(v) in seen
                or not same_placeholders(attack.payload, v.payload)
            ):
                continue
            seen.add(_payload_text(v))
            variants.append(v)
        out.extend(variants)
    return out
