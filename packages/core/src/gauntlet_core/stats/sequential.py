"""Sequential stopping for adaptive sampling with a Beta(1, 1) prior."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

Stop = Literal["stop_pass", "stop_fail", "continue", "max_reached"]


def beta_cdf(x: float, a: int, b: int) -> float:
    """P(X <= x) for X ~ Beta(a, b) with positive integer parameters, exactly, via the
    identity I_x(a, b) = P(Binomial(a + b - 1, x) >= a)."""
    if not (a >= 1 and b >= 1):
        raise ValueError("a and b must be positive integers")
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    m = a + b - 1
    return min(1.0, sum(math.comb(m, j) * x**j * (1 - x) ** (m - j) for j in range(a, m + 1)))


def posterior_mean(successes: int, trials: int) -> float:
    return (successes + 1) / (trials + 2)


@dataclass(frozen=True)
class SequentialDecision:
    decision: Stop
    p_above_hi: float  # P(p > hi)
    p_below_lo: float  # P(p < lo)
    posterior_mean: float


def sequential_decision(
    successes: int,
    trials: int,
    *,
    max_trials: int,
    min_trials: int = 3,
    hi: float = 0.9,
    lo: float = 0.5,
    confidence: float = 0.95,
) -> SequentialDecision:
    """Should we run another trial? Stop when P(p > hi) or P(p < lo) exceeds `confidence`
    (after `min_trials`), or when `max_trials` is reached."""
    if not 0 <= successes <= trials:
        raise ValueError(f"need 0 <= successes <= trials, got {successes}/{trials}")
    a, b = successes + 1, trials - successes + 1
    above = 1.0 - beta_cdf(hi, a, b)
    below = beta_cdf(lo, a, b)
    mean = posterior_mean(successes, trials)
    decision: Stop = "continue"
    if trials >= min_trials:
        if above > confidence:
            decision = "stop_pass"
        elif below > confidence:
            decision = "stop_fail"
    if decision == "continue" and trials >= max_trials:
        decision = "max_reached"
    return SequentialDecision(decision, above, below, mean)
