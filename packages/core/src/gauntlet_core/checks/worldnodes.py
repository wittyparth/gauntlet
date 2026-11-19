"""Nodes about world state: `state` and `state_diff`."""

from __future__ import annotations

from gauntlet_core.schema import (
    Evidence,
    IntRange,
    RecordChange,
    State,
    StateDiffCheck,
)

from .context import Ctx
from .matchers import match_value, resolve_path
from .registry import Res, register_node
from .support import match_values, snippet

# -- state --------------------------------------------------------------------------------


def eval_state(check: State, ctx: Ctx) -> Res:
    """Holds if some selected record's `path` matches. `id` selects one record, `where` every
    record whose fields match. The world must be known: otherwise None in prefix mode."""
    world = ctx.world
    if world is None:
        return Res(None) if ctx.prefix else Res(False)
    records = world.get(check.collection, {})
    if check.id is not None:
        selected = [(check.id, records[check.id])] if check.id in records else []
    else:
        where = check.where or {}
        selected = [
            (rid, rec)
            for rid, rec in records.items()
            if all(match_values(m, resolve_path(rec, p), ctx, None)[0] for p, m in where.items())
        ]
    for rid, rec in selected:
        values = resolve_path(rec, check.path)
        if match_values(check.matcher, values, ctx, None)[0]:
            ev = Evidence(
                seq=ctx.last_seq(),
                quote=snippet(repr(values[0])) if values else None,
                note=f"{check.collection}/{rid}.{check.path}",
            )
            # the folded world is ours and exact, so a hit counts as decided (see design 4)
            return Res(True, True, [ev])
    return Res(False)


# -- state_diff ---------------------------------------------------------------------------


def _count_ok(rng: IntRange | None, n: int) -> bool:
    return rng.contains(n) if rng is not None else True


def _explained(check: StateDiffCheck, change: RecordChange) -> bool:
    """Every changed field of the record is named in `changed` and matches its matcher."""
    wanted = check.changed or {}
    return all(f.path in wanted and match_value(wanted[f.path], f.new) for f in change.fields)


def eval_state_diff(check: StateDiffCheck, ctx: Ctx) -> Res:
    changes = ctx.diff.for_collection(check.collection) if ctx.diff else []
    added = [c for c in changes if c.kind == "added"]
    removed = [c for c in changes if c.kind == "removed"]
    changed = [c for c in changes if c.kind == "changed"]
    holds = _count_ok(check.added, len(added)) and _count_ok(check.removed, len(removed))
    for path, m in (check.changed or {}).items():
        hit = any(f.path == path and match_value(m, f.new) for c in changed for f in c.fields)
        holds = holds and hit
    if check.only:
        holds = holds and (check.added is not None or not added)
        holds = holds and (check.removed is not None or not removed)
        holds = holds and all(_explained(check, c) for c in changed)
    if not holds:
        return Res(False)
    shown = added + removed + changed
    evidence = [
        Evidence(
            seq=c.seqs[0] if c.seqs else ctx.last_seq(),
            note=f"{c.kind} {c.collection}/{c.id}",
        )
        for c in shown
        if (check.added is not None and c.kind == "added")
        or (check.removed is not None and c.kind == "removed")
        or (check.changed is not None and c.kind == "changed")
    ]
    return Res(True, True, evidence)


register_node("state", State, eval_state)
register_node("state_diff", StateDiffCheck, eval_state_diff, prefix_ok=False)
