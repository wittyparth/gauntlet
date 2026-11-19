"""The two entry points: evaluate a finished trajectory, or a prefix plus a proposed action."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from gauntlet_core.schema import Check, CheckResult, Decision, Trajectory

from .context import PrefixView, ProposedAction, ctx_from_prefix, ctx_from_trajectory
from .registry import NODES, eval_node


class NotPrefixEvaluable(ValueError):
    """The check contains a node that needs the whole trajectory (`state_diff`, `judge`)."""


def _children(check: Any) -> list[Any]:
    if check.type in ("all", "any"):
        return list(check.of)
    if check.type == "not":
        return [check.check]
    if check.type == "sequence":
        return [check.first, check.then]
    return []


def _violations(check: Any) -> list[str]:
    bad = [] if NODES[check.type].prefix_ok else [check.type]
    for child in _children(check):
        bad.extend(_violations(child))
    return bad


def is_prefix_evaluable(check: Check) -> bool:
    return not _violations(check)


def assert_prefix_evaluable(check: Check) -> None:
    """Raise NotPrefixEvaluable naming the offending node types. Called at policy load time."""
    bad = _violations(check)
    if bad:
        raise NotPrefixEvaluable(
            f"check is not evaluable before the episode ends: {', '.join(sorted(set(bad)))}"
        )


def evaluate_final(
    check: Check, traj: Trajectory, judgments: Mapping[str, bool] | None = None
) -> CheckResult:
    """Does `check` hold on the finished trajectory? `judge` nodes are resolved from
    `judgments` (rubric id -> holds); the unresolved ones are reported in `needs_judge`
    when they decide the result (three-valued logic), and then `holds` is False."""
    res = eval_node(check, ctx_from_trajectory(traj, judgments))
    return CheckResult(
        holds=res.tri is True,
        evidence=res.evidence,
        needs_judge=list(dict.fromkeys(res.judges)) if res.tri is None else [],
    )


def evaluate_prefix(check: Check, prefix: PrefixView, proposed: ProposedAction | None) -> Decision:
    """Would `proposed` make `check` hold, for good, on `prefix`?

    "violates": it holds on prefix + proposed and no extension can undo that.
    "ok": it does not hold on prefix + proposed.
    "undetermined": it depends on the future (or on data we do not have).
    """
    assert_prefix_evaluable(check)
    res = eval_node(check, ctx_from_prefix(prefix, proposed))
    if res.tri is True and res.stable:
        return "violates"
    if res.tri is False:
        return "ok"
    return "undetermined"
