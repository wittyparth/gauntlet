"""Helpers shared by the node implementations."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from gauntlet_core.schema import Evidence, Matcher, ToolCallView

from .context import Ctx, resolve_ref
from .matchers import UNRESOLVED, match_value
from .registry import Res

QUOTE_MAX = 200


@dataclass
class Hit:
    seq: int
    quote: str | None = None
    note: str | None = None

    def evidence(self) -> Evidence:
        return Evidence(seq=self.seq, quote=self.quote, note=self.note)


@dataclass
class HitSet:
    hits: list[Hit] = field(default_factory=list)
    unknown: bool = False  # something could not be decided (prefix mode only)


def snippet(text: str, start: int = 0, end: int | None = None) -> str:
    s = text[start:end]
    return s if len(s) <= QUOTE_MAX else s[:QUOTE_MAX] + "..."


def args_text(args: Any) -> str:
    return json.dumps(args, ensure_ascii=False, default=str, sort_keys=True)


def match_values(
    m: Matcher, values: list[Any], ctx: Ctx, call: ToolCallView | None
) -> tuple[bool, bool]:
    """(matched, ref_unresolved). Holds if it holds for any value, or for an absent value
    when the path led nowhere."""
    ref_value = resolve_ref(m.ref, ctx, call) if m.ref is not None else UNRESOLVED
    unresolved = m.ref is not None and ref_value is UNRESOLVED
    if not values:
        return match_value(m, None, present=False, ref_value=ref_value), unresolved
    return any(match_value(m, v, ref_value=ref_value) for v in values), unresolved


def res_from_hits(ctx: Ctx, holds: bool, hs: HitSet, *, stable: bool = True) -> Res:
    """Build a node result. In prefix mode a negative answer that rests on something unknown
    becomes None; in final mode unknowns count as "does not hold"."""
    if holds:
        return Res(True, stable, [h.evidence() for h in hs.hits])
    if hs.unknown and ctx.prefix:
        return Res(None)
    return Res(False)
