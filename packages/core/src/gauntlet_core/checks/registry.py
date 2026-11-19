"""The node table: `type -> NodeSpec`. New node types plug in without touching the walker."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from gauntlet_core.schema import Evidence

from .context import Ctx


@dataclass
class Res:
    """Three-valued node result. `tri` is True / False / None (needs a judge or, in prefix mode,
    unknown). `stable` (prefix mode): the node holds and keeps holding however the trajectory
    is extended, which is what justifies saying "violates"."""

    tri: bool | None
    stable: bool = False
    evidence: list[Evidence] = field(default_factory=list)
    judges: list[str] = field(default_factory=list)


NodeFn = Callable[[Any, Ctx], Res]
# Seqs of the events at which the node "happens" (for `sequence`). None = unresolved judge.
PointsFn = Callable[[Any, Ctx], list[int] | None]


@dataclass(frozen=True)
class NodeSpec:
    model: type
    fn: NodeFn
    prefix_ok: bool = True
    points: PointsFn | None = None


NODES: dict[str, NodeSpec] = {}


def register_node(
    type_name: str,
    model: type,
    fn: NodeFn,
    *,
    prefix_ok: bool = True,
    points: PointsFn | None = None,
) -> None:
    NODES[type_name] = NodeSpec(model, fn, prefix_ok, points)


def eval_node(check: Any, ctx: Ctx) -> Res:
    return NODES[check.type].fn(check, ctx)


def first_hold_points(check: Any, ctx: Ctx) -> list[int] | None:
    """The first event at which the node holds on the prefix ending there ([] if never,
    None if that depends on an unresolved judge)."""
    saw_unknown = False
    for e in ctx.events:
        res = eval_node(check, ctx.upto(e.seq))
        if res.tri is True:
            return [e.seq]
        saw_unknown = saw_unknown or res.tri is None
    return None if saw_unknown else []


def event_points(check: Any, ctx: Ctx) -> list[int] | None:
    """Seqs at which `check` is satisfied by a single event (None = unresolved judge)."""
    spec = NODES[check.type]
    if spec.points is not None:
        return spec.points(check, ctx)
    return first_hold_points(check, ctx)
