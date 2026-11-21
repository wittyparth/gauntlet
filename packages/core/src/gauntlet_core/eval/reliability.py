"""The reliability curve (pass^k for k = 1..k_max) in report form. The estimator and the
cluster bootstrap are `gauntlet_core.stats`'; this only reshapes and truncates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from gauntlet_core.stats import reliability_curve as _curve

__all__ = ["ReliabilityPoint", "reliability_curve"]

HINT = "increase repetitions to see reliability"


class ReliabilityPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    k: int
    value: float
    ci_low: float
    ci_high: float
    scenarios: int  # scenarios with at least k trials; the others are left out of this point


def reliability_curve(
    per_scenario: Mapping[str, Sequence[bool]],
    *,
    seed: int,
    resamples: int = 2000,
    k_max: int = 8,
) -> list[ReliabilityPoint]:
    """`k_max = min(k_max, max n)`. With every scenario at n = 1 the curve is the single point
    k = 1 (callers show `HINT`)."""
    pts = _curve(per_scenario, resamples=resamples, seed=seed)
    return [
        ReliabilityPoint(
            k=p.k,
            value=p.estimate.value,
            ci_low=p.estimate.low,
            ci_high=p.estimate.high,
            scenarios=p.estimate.n,
        )
        for p in pts
        if p.k <= k_max
    ]
