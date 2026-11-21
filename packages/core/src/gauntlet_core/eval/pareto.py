"""Pareto frontier over run summaries (P3-8). Point estimates decide dominance; the pass-rate
intervals decide whether a dominance is statistically supported."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

__all__ = ["METRICS", "ParetoPoint", "ParetoResult", "pareto_frontier"]

# metric -> True when larger is better
METRICS: dict[str, bool] = {"pass_rate": True, "cost": False, "latency_p95": False}


class ParetoPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    agent_version_id: str
    label: str
    model: str | None = None
    pass_rate: float | None
    ci_low: float | None
    ci_high: float | None
    cost_per_episode_usd_micros: int
    latency_p95_ms: int | None


class ParetoResult(ParetoPoint):
    on_frontier: bool
    dominated_by: list[str]
    dominance_supported: bool


Metric = Literal["pass_rate", "cost", "latency_p95"]


def _value(p: ParetoPoint, metric: str) -> float:
    """Oriented so that larger is better; a missing value is the worst possible."""
    if metric == "pass_rate":
        return p.pass_rate if p.pass_rate is not None else float("-inf")
    if metric == "cost":
        return -float(p.cost_per_episode_usd_micros)
    return -float(p.latency_p95_ms) if p.latency_p95_ms is not None else float("-inf")


def _dominates(a: ParetoPoint, b: ParetoPoint, metrics: Sequence[str]) -> bool:
    av = [_value(a, m) for m in metrics]
    bv = [_value(b, m) for m in metrics]
    return all(x >= y for x, y in zip(av, bv, strict=True)) and any(
        x > y for x, y in zip(av, bv, strict=True)
    )


def _overlap(a: ParetoPoint, b: ParetoPoint) -> bool:
    if None in (a.ci_low, a.ci_high, b.ci_low, b.ci_high):
        return True  # unknown interval: cannot claim the dominance is established
    assert a.ci_low is not None and a.ci_high is not None
    assert b.ci_low is not None and b.ci_high is not None
    return a.ci_low <= b.ci_high and b.ci_low <= a.ci_high


def pareto_frontier(points: Sequence[ParetoPoint], metrics: Sequence[str]) -> list[ParetoResult]:
    """Input order is kept. A point is on the frontier when no other point is at least as good
    on every metric and strictly better on one. `dominance_supported` is False for a dominated
    point when its pass-rate interval overlaps that of every dominator."""
    unknown = [m for m in metrics if m not in METRICS]
    if unknown or not metrics:
        raise ValueError(f"metrics must be a non-empty subset of {sorted(METRICS)}")
    out: list[ParetoResult] = []
    for p in points:
        doms = [q for q in points if q is not p and _dominates(q, p, metrics)]
        out.append(
            ParetoResult(
                **p.model_dump(),
                on_frontier=not doms,
                dominated_by=[q.run_id for q in doms],
                dominance_supported=bool(doms) and any(not _overlap(p, q) for q in doms),
            )
        )
    return out
