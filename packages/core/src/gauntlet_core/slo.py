"""Service-level objectives with error budgets and multi-window burn rates (P5-7).

A sample is one event that either met the objective (`good`) or did not. The objective is the
required fraction of good events over the window. Compliance carries a Wilson interval: a
breach needs the interval to exclude the objective (the whole interval lies below it); a
warning needs only the point estimate below it. An empty window is `unknown`, never `ok`.

Burn rate is the bad fraction in a short window divided by the allowed bad fraction
(`1 - objective`); 1.0 spends the budget exactly over the window. Alert pairs follow the usual
fast and slow burn pattern: both windows of a pair must exceed the pair's rate."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from .stats.intervals import wilson_interval

__all__ = [
    "BURN_PAIRS",
    "BURN_WINDOWS",
    "MAX_BURN",
    "Sample",
    "SloStatus",
    "burn_alerts",
    "slo_status",
]

BURN_WINDOWS: dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "3d": timedelta(days=3),
}
# (name, short window, long window, burn rate both must reach)
BURN_PAIRS: tuple[tuple[str, str, str, float], ...] = (
    ("fast", "1h", "6h", 14.4),
    ("slow", "6h", "3d", 6.0),
)
MAX_BURN = 1000.0  # reported when the objective allows no bad events and one occurred


@dataclass(frozen=True)
class Sample:
    ts: datetime
    good: bool


@dataclass(frozen=True)
class SloStatus:
    state: Literal["ok", "warning", "breached", "unknown"]
    n: int
    compliance: float | None
    interval: tuple[float, float] | None
    error_budget_remaining: float | None  # 1 = untouched, 0 = spent, negative = overspent
    burn_rates: dict[str, float] = field(default_factory=dict)  # windows that hold samples
    breached: bool = False
    warning: bool = False


def _bad_fraction(samples: Sequence[Sample]) -> float:
    return sum(1 for s in samples if not s.good) / len(samples)


def _burn(bad_fraction: float, allowed: float) -> float:
    if allowed <= 0:
        return MAX_BURN if bad_fraction > 0 else 0.0
    return min(bad_fraction / allowed, MAX_BURN)


def slo_status(
    samples: Sequence[Sample], objective: float, window: timedelta, now: datetime
) -> SloStatus:
    if not 0.0 < objective <= 1.0:
        raise ValueError("objective must be in (0, 1]")
    in_window = [s for s in samples if now - window <= s.ts <= now]
    if not in_window:
        return SloStatus("unknown", 0, None, None, None)
    n = len(in_window)
    good = sum(1 for s in in_window if s.good)
    compliance = good / n
    lo, hi = wilson_interval(good, n)
    allowed = 1.0 - objective
    bad = _bad_fraction(in_window)
    budget = (1.0 if bad == 0 else 0.0) if allowed <= 0 else 1.0 - bad / allowed
    burns: dict[str, float] = {}
    for name, span in BURN_WINDOWS.items():
        sub = [s for s in in_window if now - span <= s.ts <= now]
        if sub:
            burns[name] = _burn(_bad_fraction(sub), allowed)
    breached = hi < objective
    warning = not breached and compliance < objective
    state: Literal["ok", "warning", "breached"] = (
        "breached" if breached else "warning" if warning else "ok"
    )
    return SloStatus(state, n, compliance, (lo, hi), budget, burns, breached, warning)


def burn_alerts(status: SloStatus) -> list[str]:
    """Names of the burn pairs currently firing (`fast`, `slow`)."""
    out: list[str] = []
    for name, short, long, rate in BURN_PAIRS:
        if status.burn_rates.get(short, 0.0) >= rate and status.burn_rates.get(long, 0.0) >= rate:
            out.append(name)
    return out
