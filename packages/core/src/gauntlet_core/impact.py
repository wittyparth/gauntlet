"""Change impact: which scenarios to re-run after a change (P5-7).

Conservative and self-explaining. Every selected scenario carries at least one reason. Pinned
regressions are always selected when anything changed. An unknown change class selects
everything (`full_run`). An unchanged version selects nothing."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "Change",
    "ImpactHistory",
    "ImpactSet",
    "ScenarioInfo",
    "classify_change",
    "compute_impact",
]

SAMPLE_FRACTION = 0.25  # of each risk stratum, at least one scenario per non-empty stratum
RISKS = ("high", "medium", "low")
_CLASSIFIED_KEYS = {"model", "system_prompt", "tools", "temperature"}


@dataclass(frozen=True)
class Change:
    tools: frozenset[str] = frozenset()  # tools added, removed or whose schema changed
    policy_clauses: frozenset[str] = frozenset()
    model: bool = False
    prompt: bool = False
    worlds: frozenset[str] = frozenset()
    unknown: bool = False

    @property
    def empty(self) -> bool:
        return not (
            self.tools
            or self.policy_clauses
            or self.model
            or self.prompt
            or self.worlds
            or self.unknown
        )


@dataclass(frozen=True)
class ScenarioInfo:
    id: str
    tools: frozenset[str] = frozenset()  # referenced by checks or called in past episodes
    tags: Mapping[str, str] = field(default_factory=dict)
    world_id: str | None = None
    risk: str = "medium"  # high, medium or low
    pinned: bool = False  # a pinned regression


@dataclass(frozen=True)
class ImpactHistory:
    scenarios: tuple[ScenarioInfo, ...]
    flipped_recent: frozenset[str] = frozenset()  # flipped pass/fail within the last 5 runs


@dataclass(frozen=True)
class ImpactSet:
    scenario_ids: list[str]
    reasons: dict[str, list[str]]
    full_run: bool


def _tool_names(tools: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for t in tools or []:
        if isinstance(t, str):
            out[t] = t
        elif isinstance(t, Mapping) and isinstance(t.get("name"), str):
            out[t["name"]] = t
    return out


def classify_change(
    old: Mapping[str, Any],
    new: Mapping[str, Any],
    *,
    policy_clauses: frozenset[str] = frozenset(),
    worlds: frozenset[str] = frozenset(),
) -> Change:
    """Compare two agent version configs. Keys outside the known set that differ (a changed
    endpoint, headers, an unrecognised field) make the class unknown."""
    old_t, new_t = _tool_names(old.get("tools")), _tool_names(new.get("tools"))
    tools = frozenset(n for n in old_t.keys() | new_t.keys() if old_t.get(n) != new_t.get(n))
    unknown = any(old.get(k) != new.get(k) for k in (old.keys() | new.keys()) - _CLASSIFIED_KEYS)
    return Change(
        tools=tools,
        policy_clauses=policy_clauses,
        model=old.get("model") != new.get("model")
        or old.get("temperature") != new.get("temperature"),
        prompt=old.get("system_prompt") != new.get("system_prompt"),
        worlds=worlds,
        unknown=unknown,
    )


def _rank(seed: str, sid: str) -> str:
    return hashlib.sha256(f"{seed}:{sid}".encode()).hexdigest()


def compute_impact(change: Change, history: ImpactHistory, *, seed: str = "impact") -> ImpactSet:
    scenarios = history.scenarios
    reasons: dict[str, list[str]] = {}

    def add(sid: str, why: str) -> None:
        bucket = reasons.setdefault(sid, [])
        if why not in bucket:
            bucket.append(why)

    if change.empty:
        return ImpactSet([], {}, False)
    if change.unknown:
        for s in scenarios:
            add(s.id, "unknown change class: full run")
        return ImpactSet(sorted(reasons), reasons, True)

    for s in scenarios:
        if s.pinned:
            add(s.id, "pinned regression")
        for t in sorted(change.tools & s.tools):
            add(s.id, f"references changed tool {t}")
        if change.policy_clauses:
            tagged = set(s.tags.values()) | set(s.tags)
            for c in sorted(change.policy_clauses & tagged):
                add(s.id, f"tagged with changed policy clause {c}")
        if s.world_id is not None and s.world_id in change.worlds:
            add(s.id, f"uses changed world {s.world_id}")

    if change.model or change.prompt:
        what = "model" if change.model else "prompt"
        for risk in RISKS:
            stratum = sorted((s for s in scenarios if s.risk == risk), key=lambda s: s.id)
            if not stratum:
                continue
            take = max(1, math.ceil(len(stratum) * SAMPLE_FRACTION))
            for s in sorted(stratum, key=lambda s: _rank(seed, s.id))[:take]:
                add(s.id, f"{what} change: {risk}-risk sample")
        for s in scenarios:
            if s.id in history.flipped_recent:
                add(s.id, f"{what} change: flipped in the last 5 runs")

    return ImpactSet(sorted(reasons), reasons, False)
