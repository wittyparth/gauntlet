"""Failure score of one production conversation (P5-2)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from gauntlet_core.checks import detectors as registry
from gauntlet_core.schema import Event, Json, Model, StateDiff, Trajectory

from . import signals

__all__ = ["WEIGHTS", "DetectorSpec", "FailureScore", "SampledJudge", "score_conversation"]

# How much each part can pull the total up; a detector hit alone is worth at least 0.6.
WEIGHTS = {
    "detector": 1.0,
    "redaction_leak": 0.9,
    "human_request": 0.7,
    "judge": 0.8,
    "dissatisfaction": 0.6,
    "rephrasing": 0.5,
    "abandonment": 0.4,
}
SampledJudge = Callable[[Sequence[Event]], Awaitable[float | None]]


class DetectorSpec(Model):
    name: str
    params: Json = {}


class FailureScore(Model):
    total: float
    parts: dict[str, float]
    reasons: list[str]
    detector_hits: list[str] = []  # names of the detectors that fired


@dataclass
class _Acc:
    parts: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


def _trajectory(events: Sequence[Event]) -> Trajectory:
    return Trajectory.model_construct(
        episode_id="prod", scenario=None, events=list(events), initial_world={}, final_world={},
        diff=StateDiff(), canaries=[], tool_risk={}, honeytools=[],
    )  # fmt: skip


async def score_conversation(
    events: Sequence[Event],
    detectors: Sequence[DetectorSpec],
    *,
    judge: SampledJudge | None = None,
) -> FailureScore:
    acc = _Acc()
    traj = _trajectory(events)
    fired: list[str] = []
    hits = 0
    for d in detectors:
        res = registry.get(d.name)(traj, d.params)
        if res.holds:
            fired.append(d.name)
            hits += max(1, len(res.evidence))
            acc.reasons.append(f"detector {d.name}: {len(res.evidence)} hit(s)")
    if fired:
        acc.parts["detector"] = min(1.0, 0.6 + 0.1 * (hits - 1))
    for name, fn in (
        ("rephrasing", signals.rephrasing),
        ("dissatisfaction", signals.dissatisfaction),
        ("human_request", signals.human_request),
        ("abandonment", signals.abandonment),
        ("redaction_leak", signals.redaction_leak),
    ):
        value, why = fn(events)
        if value > 0:
            acc.parts[name] = value
            acc.reasons += why
    if judge is not None:
        verdict = await judge(events)
        if verdict is not None and verdict > 0:
            acc.parts["judge"] = min(1.0, verdict)
            acc.reasons.append("calibrated rubric judged the conversation a failure")
    keep = 1.0
    for part, value in acc.parts.items():
        keep *= 1.0 - WEIGHTS[part] * min(1.0, value)
    total = round(1.0 - keep, 6)
    return FailureScore(total=total, parts=acc.parts, reasons=acc.reasons, detector_hits=fired)


def part_names(score: FailureScore) -> list[str]:
    return sorted(score.parts)


def as_params(spec: Mapping[str, Any]) -> DetectorSpec:
    return DetectorSpec.model_validate(spec)
