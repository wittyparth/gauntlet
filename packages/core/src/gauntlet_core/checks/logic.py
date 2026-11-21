"""Combinators and nodes without a world: all, any, not, sequence, detector, judge."""

from __future__ import annotations

from gauntlet_core.schema import All, Any_, Detector, Evidence, Judge, Not, Sequence

from . import detectors
from .context import Ctx
from .registry import Res, eval_node, event_points, register_node
from .support import Hit, HitSet, res_from_hits

SUBSTANTIVE = ("tool_call", "agent_message")


def _dedup(ids: list[str]) -> list[str]:
    return list(dict.fromkeys(ids))


def eval_all(check: All, ctx: Ctx) -> Res:
    results = [eval_node(c, ctx) for c in check.of]
    if any(r.tri is False for r in results):
        return Res(False)
    if any(r.tri is None for r in results):
        return Res(None, judges=_dedup([j for r in results if r.tri is None for j in r.judges]))
    evidence = [e for r in results for e in r.evidence]
    return Res(True, all(r.stable for r in results), evidence)


def eval_any(check: Any_, ctx: Ctx) -> Res:
    results = [eval_node(c, ctx) for c in check.of]
    holding = [r for r in results if r.tri is True]
    if holding:
        return Res(True, any(r.stable for r in holding), [e for r in holding for e in r.evidence])
    if any(r.tri is None for r in results):
        return Res(None, judges=_dedup([j for r in results if r.tri is None for j in r.judges]))
    return Res(False)


def eval_not(check: Not, ctx: Ctx) -> Res:
    inner = eval_node(check.check, ctx)
    if ctx.prefix:
        # Not(inner) holds now only while inner has not happened, and inner may still happen:
        # the only decided outcome is "inner already holds for good, so Not never will".
        if inner.tri is True and inner.stable:
            return Res(False, evidence=inner.evidence)
        return Res(None)
    if inner.tri is None:
        return Res(None, judges=inner.judges)
    return Res(not inner.tri, evidence=inner.evidence)


def _next_substantive(ctx: Ctx, seq: int) -> int | None:
    return next((e.seq for e in ctx.events if e.seq > seq and e.kind in SUBSTANTIVE), None)


def eval_sequence(check: Sequence, ctx: Ctx) -> Res:
    firsts = event_points(check.first, ctx)
    thens = event_points(check.then, ctx)
    if firsts == [] or thens == []:
        return Res(False)
    if firsts is None or thens is None:
        judges = _dedup(
            [
                j
                for c, pts in ((check.first, firsts), (check.then, thens))
                if pts is None
                for j in eval_node(c, ctx).judges
            ]
        )
        return Res(None, judges=judges)
    pair: tuple[int, int] | None = None
    if check.strict:
        for f in firsts:
            nxt = _next_substantive(ctx, f)
            if nxt is not None and nxt in thens:
                pair = (f, nxt)
                break
    else:
        f = min(firsts)
        later = [t for t in thens if t > f]
        if later:
            pair = (f, min(later))
    if pair is None:
        return Res(False)
    return Res(
        True,
        True,
        [Evidence(seq=pair[0], note="first"), Evidence(seq=pair[1], note="then")],
    )


def eval_detector(check: Detector, ctx: Ctx) -> Res:
    result = detectors.get(check.name)(ctx.trajectory(), check.params)
    if not result.holds and result.needs_judge and ctx.prefix:
        return Res(None)  # a detector that could not finish (latency budget, no model): unknown
    hs = HitSet([Hit(e.seq, e.quote, e.note) for e in result.evidence])
    return res_from_hits(ctx, result.holds, hs)


def detector_points(check: Detector, ctx: Ctx) -> list[int] | None:
    result = detectors.get(check.name)(ctx.trajectory(), check.params)
    return sorted({e.seq for e in result.evidence}) if result.holds else []


def eval_judge(check: Judge, ctx: Ctx) -> Res:
    verdict = ctx.judgments.get(check.rubric)
    if verdict is None:
        return Res(None, judges=[check.rubric])
    return Res(verdict, False)


register_node("all", All, eval_all)
register_node("any", Any_, eval_any)
register_node("not", Not, eval_not)
register_node("sequence", Sequence, eval_sequence)
register_node("detector", Detector, eval_detector, points=detector_points)
register_node("judge", Judge, eval_judge, prefix_ok=False)
