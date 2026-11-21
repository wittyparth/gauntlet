"""Trajectory diff (P3-1): Needleman-Wunsch alignment of two trajectories' steps."""

from __future__ import annotations

import json
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from gauntlet_core.schema import StateDiff, Trajectory
from gauntlet_core.schema.journal import tool_call_views

__all__ = ["DiffRow", "StateDiffCompare", "StateKey", "TrajectoryDiff", "diff_trajectories"]

CAP = 200
GAP = -1
MIN_RATIO = 0.6
Status = Literal["same", "changed", "only_a", "only_b"]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DiffRow(_M):
    status: Status
    a_seq: int | None
    b_seq: int | None
    kind: Literal["user_message", "agent_message", "tool_call"]
    summary_a: str | None
    summary_b: str | None
    similarity: float | None = None


class StateKey(_M):
    collection: str
    id: str
    path: str
    value_a: Any = None
    value_b: Any = None


class StateDiffCompare(_M):
    only_a: list[StateKey]
    only_b: list[StateKey]
    differing: list[StateKey]


class TrajectoryDiff(_M):
    rows: list[DiffRow]
    first_divergence: tuple[int | None, int | None] | None
    state_diff: StateDiffCompare
    truncated: bool


@dataclass(frozen=True)
class _Step:
    kind: Literal["user_message", "agent_message", "tool_call"]
    seq: int
    text: str  # message text, or the tool name
    args: str  # canonical args (tool calls)
    summary: str


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _steps(t: Trajectory) -> list[_Step]:
    calls = {c.call_seq: c for c in tool_call_views(t.events)}
    out: list[_Step] = []
    for e in t.events:
        if e.kind in ("user_message", "agent_message"):
            text = str(e.payload.get("text", ""))
            out.append(_Step(e.kind, e.seq, text, "", text))  # type: ignore[arg-type]
        elif e.kind == "tool_call" and e.seq in calls:
            c = calls[e.seq]
            res = "error: " + str(c.error) if c.ok is False else _canon(c.result)
            summary = f"{c.tool}({_canon(c.args)}) -> {res}"
            out.append(_Step("tool_call", e.seq, c.tool, _canon(c.args), summary))
    return out


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def _match(a: _Step, b: _Step) -> tuple[int, Status, float] | None:
    """(score, status, similarity) when the two steps may align, else None."""
    if a.kind != b.kind:
        return None
    if a.kind == "tool_call":
        if a.text != b.text:
            return None
        return (2, "same", 1.0) if a.args == b.args else (1, "changed", 0.5)
    ratio = SequenceMatcher(None, _norm(a.text), _norm(b.text)).ratio()
    if ratio < MIN_RATIO:
        return None
    exact = _norm(a.text) == _norm(b.text)
    return (2 if ratio >= 0.9 else 1, "same" if exact else "changed", ratio)


def _align(a: list[_Step], b: list[_Step]) -> list[DiffRow]:
    n, m = len(a), len(b)
    score = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        score[i][0] = i * GAP
    for j in range(1, m + 1):
        score[0][j] = j * GAP
    matches: dict[tuple[int, int], tuple[int, Status, float] | None] = {}
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            mt = _match(a[i - 1], b[j - 1])
            matches[(i, j)] = mt
            best = max(score[i - 1][j], score[i][j - 1]) + GAP
            if mt:
                best = max(best, score[i - 1][j - 1] + mt[0])
            score[i][j] = best
    rows: list[DiffRow] = []
    i, j = n, m
    while i > 0 or j > 0:
        mt = matches.get((i, j)) if i > 0 and j > 0 else None
        if mt and score[i][j] == score[i - 1][j - 1] + mt[0]:
            sa, sb = a[i - 1], b[j - 1]
            rows.append(
                DiffRow(
                    status=mt[1],
                    a_seq=sa.seq,
                    b_seq=sb.seq,
                    kind=sa.kind,
                    summary_a=sa.summary,
                    summary_b=sb.summary,
                    similarity=mt[2],
                )
            )
            i, j = i - 1, j - 1
        elif i > 0 and score[i][j] == score[i - 1][j] + GAP:
            sa = a[i - 1]
            rows.append(
                DiffRow(
                    status="only_a",
                    a_seq=sa.seq,
                    b_seq=None,
                    kind=sa.kind,
                    summary_a=sa.summary,
                    summary_b=None,
                )
            )
            i -= 1
        else:
            sb = b[j - 1]
            rows.append(
                DiffRow(
                    status="only_b",
                    a_seq=None,
                    b_seq=sb.seq,
                    kind=sb.kind,
                    summary_a=None,
                    summary_b=sb.summary,
                )
            )
            j -= 1
    rows.reverse()
    return rows


def _state_entries(diff: StateDiff) -> dict[tuple[str, str, str], Any]:
    out: dict[tuple[str, str, str], Any] = {}
    for c in diff.changes:
        if c.kind == "changed":
            for f in c.fields:
                out[(c.collection, c.id, f.path)] = {"new": f.new}
        else:
            out[(c.collection, c.id, "")] = {c.kind: c.record}
    return out


def _compare_state(a: StateDiff, b: StateDiff) -> StateDiffCompare:
    ea, eb = _state_entries(a), _state_entries(b)
    only_a = [
        StateKey(collection=k[0], id=k[1], path=k[2], value_a=v)
        for k, v in sorted(ea.items())
        if k not in eb
    ]
    only_b = [
        StateKey(collection=k[0], id=k[1], path=k[2], value_b=v)
        for k, v in sorted(eb.items())
        if k not in ea
    ]
    differing = [
        StateKey(collection=k[0], id=k[1], path=k[2], value_a=ea[k], value_b=eb[k])
        for k in sorted(ea)
        if k in eb and _canon(ea[k]) != _canon(eb[k])
    ]
    return StateDiffCompare(only_a=only_a, only_b=only_b, differing=differing)


def diff_trajectories(a: Trajectory, b: Trajectory) -> TrajectoryDiff:
    sa, sb = _steps(a), _steps(b)
    truncated = len(sa) > CAP or len(sb) > CAP
    rows = _align(sa[:CAP], sb[:CAP])
    first = next((r for r in rows if r.status != "same"), None)
    return TrajectoryDiff(
        rows=rows,
        first_divergence=(first.a_seq, first.b_seq) if first else None,
        state_diff=_compare_state(a.diff, b.diff),
        truncated=truncated,
    )
