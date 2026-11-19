"""Paired comparison of two runs, permutation test, and the per-scenario flip table."""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import product
from typing import Literal

from .intervals import Estimate, percentile

Verdict = Literal["regression", "improvement", "no detectable change", "inconclusive"]
FlipCategory = Literal["newly_failing", "newly_passing", "flaky", "stable"]
EXACT_LIMIT = 14  # up to 2**14 sign patterns are enumerated, beyond that Monte Carlo
Data = Mapping[str, Sequence[bool]]


def _rate(trials: Sequence[bool]) -> float:
    return sum(1 for t in trials if t) / len(trials)


def sign_flip_pvalue(diffs: Sequence[float], *, seed: int = 0, samples: int = 20000) -> float:
    """Two-sided sign-flip permutation p-value for mean(diffs) == 0. Always in (0, 1]."""
    ds = [d for d in diffs if d != 0.0]
    if not ds:
        return 1.0
    observed = abs(sum(ds))
    tol = 1e-12 * max(1.0, observed)
    if len(ds) <= EXACT_LIMIT:
        total = 2 ** len(ds)
        hits = sum(
            1
            for signs in product((1, -1), repeat=len(ds))
            if abs(sum(s * d for s, d in zip(signs, ds, strict=True))) >= observed - tol
        )
        return hits / total
    rng = random.Random(seed)
    hits = 0
    for _ in range(samples):
        if abs(sum(d if rng.random() < 0.5 else -d for d in ds)) >= observed - tol:
            hits += 1
    return (hits + 1) / (samples + 1)


@dataclass(frozen=True)
class Comparison:
    verdict: Verdict
    delta: Estimate  # mean over shared scenarios of rate_B - rate_A
    p_value: float
    margin: float
    n_scenarios: int
    message: str


def compare_runs(
    a: Data,
    b: Data,
    *,
    margin: float = 0.02,
    resamples: int = 2000,
    seed: int = 0,
) -> Comparison:
    """Baseline `a` versus candidate `b`, paired by scenario."""
    shared = sorted(s for s in set(a) & set(b) if a[s] and b[s])
    if not shared:
        return Comparison(
            "inconclusive", Estimate(0.0, -1.0, 1.0, 0), 1.0, margin, 0, "no shared scenarios"
        )
    diffs = [_rate(b[s]) - _rate(a[s]) for s in shared]
    m = len(diffs)
    mean = sum(diffs) / m
    rng = random.Random(seed)
    boots = sorted(sum(diffs[rng.randrange(m)] for _ in range(m)) / m for _ in range(resamples))
    low = min(percentile(boots, 0.025), mean)
    high = max(percentile(boots, 0.975), mean)
    p = sign_flip_pvalue(diffs, seed=seed)
    eps = 1e-12
    if high < -margin - eps:
        verdict: Verdict = "regression"
    elif low > margin + eps:
        verdict = "improvement"
    elif low >= -margin - eps and high <= margin + eps:
        verdict = "no detectable change"
    else:
        verdict = "inconclusive"
    half = (high - low) / 2
    reps = sum(len(a[s]) + len(b[s]) for s in shared) / (2 * m)
    message = _message(verdict, mean, half, margin, reps)
    return Comparison(verdict, Estimate(mean, low, high, m), p, margin, m, message)


def _message(verdict: Verdict, mean: float, half: float, margin: float, reps: float) -> str:
    if verdict != "inconclusive":
        return f"{verdict}: change of {mean * 100:+.1f} points (margin {margin * 100:.1f})"
    needed = math.ceil(reps * (half / margin) ** 2) if margin > 0 else math.ceil(reps * 4)
    extra = max(1, needed - math.ceil(reps))
    return (
        f"this run could detect a change of about {half * 100:.1f} points; "
        f"run {extra} more repetitions to detect {margin * 100:.1f}"
    )


def fisher_exact(a_succ: int, a_n: int, b_succ: int, b_n: int) -> float:
    """Two-sided Fisher exact p-value for a 2x2 table (sum of tables no more likely)."""
    total = a_n + b_n
    succ = a_succ + b_succ
    denom = math.comb(total, succ)

    def prob(x: int) -> float:
        return math.comb(a_n, x) * math.comb(b_n, succ - x) / denom

    lo, hi = max(0, succ - b_n), min(a_n, succ)
    p_obs = prob(a_succ)
    return min(1.0, sum(p for x in range(lo, hi + 1) if (p := prob(x)) <= p_obs * (1 + 1e-7)))


@dataclass(frozen=True)
class Flip:
    scenario_id: str
    category: FlipCategory
    rate_a: float
    rate_b: float
    p_value: float | None = None
    note: str | None = None


def classify_flip(scenario_id: str, a: Sequence[bool], b: Sequence[bool]) -> Flip:
    ra, rb = _rate(a), _rate(b)
    if len(a) == 1 and len(b) == 1 and ra != rb:
        cat: FlipCategory = "newly_failing" if ra > rb else "newly_passing"
        return Flip(scenario_id, cat, ra, rb, None, "single trial")
    p = fisher_exact(sum(a), len(a), sum(b), len(b))
    if ra >= 0.8 and rb <= 0.2 and p < 0.1:
        return Flip(scenario_id, "newly_failing", ra, rb, p)
    if rb >= 0.8 and ra <= 0.2 and p < 0.1:
        return Flip(scenario_id, "newly_passing", ra, rb, p)
    if 0 < ra < 1 and 0 < rb < 1:
        return Flip(scenario_id, "flaky", ra, rb, p)
    note = None
    if (ra >= 0.8 and rb <= 0.2) or (rb >= 0.8 and ra <= 0.2):
        note = "large change but too few trials to confirm"
    return Flip(scenario_id, "stable", ra, rb, p, note)


def flip_table(a: Data, b: Data) -> list[Flip]:
    """Per shared scenario classification, sorted by scenario id."""
    return [classify_flip(s, a[s], b[s]) for s in sorted(set(a) & set(b)) if a[s] and b[s]]
