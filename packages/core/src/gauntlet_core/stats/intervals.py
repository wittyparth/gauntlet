"""Interval estimates for rates: Wilson score and the shared percentile helper."""

from __future__ import annotations

import math
from dataclasses import dataclass

Z95 = 1.959963984540054


@dataclass(frozen=True)
class Estimate:
    """A point estimate with a 95 percent interval. `n` is the number of scenarios or trials."""

    value: float
    low: float
    high: float
    n: int = 0

    @property
    def half_width(self) -> float:
        return (self.high - self.low) / 2


def wilson_interval(successes: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion. `n == 0` gives the vacuous (0, 1)."""
    if n < 0 or successes < 0 or successes > n:
        raise ValueError(f"need 0 <= successes <= n, got {successes}/{n}")
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def wilson_estimate(successes: int, n: int, z: float = Z95) -> Estimate:
    low, high = wilson_interval(successes, n, z)
    return Estimate(successes / n if n else 0.0, low, high, n)


def percentile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolated percentile (q in [0, 1]) of an already sorted, non-empty list."""
    if not sorted_values:
        raise ValueError("percentile of empty list")
    pos = q * (len(sorted_values) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    frac = pos - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac
