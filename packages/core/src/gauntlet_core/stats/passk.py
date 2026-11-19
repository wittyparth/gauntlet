"""Pass rates and the unbiased pass^k estimator, with cluster-bootstrap intervals.

Inputs are `dict[scenario_id, list[bool]]` of scored episodes (passed or failed only).
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from .intervals import Estimate, percentile, wilson_interval

DEFAULT_RESAMPLES = 2000
MAX_K = 8
Counts = list[tuple[int, int]]  # per scenario: (successes c, trials n)


def pass_hat_k(c: int, n: int, k: int) -> float:
    """Unbiased estimate of p^k from c successes in n trials: C(c, k) / C(n, k)."""
    if not 1 <= k <= n:
        raise ValueError(f"need 1 <= k <= n, got k={k}, n={n}")
    if not 0 <= c <= n:
        raise ValueError(f"need 0 <= c <= n, got c={c}, n={n}")
    return math.comb(c, k) / math.comb(n, k)


def to_counts(data: Mapping[str, Sequence[bool]]) -> Counts:
    out = [(sum(1 for x in trials if x), len(trials)) for _, trials in sorted(data.items())]
    return [(c, n) for c, n in out if n > 0]


def rate_stat(counts: Counts) -> float:
    return sum(c / n for c, n in counts) / len(counts)


def passk_stat(k: int) -> Callable[[Counts], float]:
    def stat(counts: Counts) -> float:
        usable = [(c, n) for c, n in counts if n >= k]
        return sum(pass_hat_k(c, n, k) for c, n in usable) / len(usable) if usable else 0.0

    return stat


def bootstrap_counts(
    counts: Counts,
    stats: Sequence[Callable[[Counts], float]],
    *,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = 0,
) -> list[list[float]]:
    """Cluster bootstrap: resample scenarios with replacement, then each one's trials with
    replacement. Returns, per statistic, the sorted list of resampled values."""
    rng = random.Random(seed)
    m = len(counts)
    out: list[list[float]] = [[] for _ in stats]
    for _ in range(resamples):
        sample: Counts = []
        for _ in range(m):
            c, n = counts[rng.randrange(m)]
            p = c / n
            sample.append((sum(1 for _ in range(n) if rng.random() < p), n))
        for i, stat in enumerate(stats):
            out[i].append(stat(sample))
    for values in out:
        values.sort()
    return out


def _estimate(counts: Counts, stat: Callable[[Counts], float], boot: list[float]) -> Estimate:
    """Percentile interval of the bootstrap, widened to contain the point estimate.

    Degenerate case: when every outcome is identical (for example 0 of 4 passes) all
    resamples coincide and the percentile interval collapses to a single point, which
    claims certainty the data cannot support. Whenever the bootstrap interval has zero
    width we fall back to the Wilson score interval on the pooled counts (sum of
    successes over sum of trials). The reported interval is therefore never zero-width
    for a non-empty sample (0 of 4 gives roughly 0% to 49%).
    """
    low, high = percentile(boot, 0.025), percentile(boot, 0.975)
    if high - low <= 1e-12:
        low, high = wilson_interval(sum(c for c, _ in counts), sum(n for _, n in counts))
    value = stat(counts)
    return Estimate(value, min(low, value), max(high, value), len(counts))


def suite_pass_rate(
    data: Mapping[str, Sequence[bool]], *, resamples: int = DEFAULT_RESAMPLES, seed: int = 0
) -> Estimate:
    """Mean of per-scenario pass rates, with a cluster-bootstrap percentile interval."""
    counts = to_counts(data)
    if not counts:
        return Estimate(0.0, 0.0, 1.0, 0)
    (boot,) = bootstrap_counts(counts, [rate_stat], resamples=resamples, seed=seed)
    return _estimate(counts, rate_stat, boot)


def suite_pass_hat_k(
    data: Mapping[str, Sequence[bool]],
    k: int,
    *,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = 0,
) -> Estimate:
    """Mean over scenarios with at least k trials of C(c,k)/C(n,k)."""
    counts = [(c, n) for c, n in to_counts(data) if n >= k]
    if not counts:
        return Estimate(0.0, 0.0, 1.0, 0)
    stat = passk_stat(k)
    (boot,) = bootstrap_counts(counts, [stat], resamples=resamples, seed=seed)
    return _estimate(counts, stat, boot)


@dataclass(frozen=True)
class ReliabilityPoint:
    k: int
    estimate: Estimate


def reliability_curve(
    data: Mapping[str, Sequence[bool]], *, resamples: int = DEFAULT_RESAMPLES, seed: int = 0
) -> list[ReliabilityPoint]:
    """Suite pass^k for k = 1..min(max n, 8). A scenario with fewer than k trials is left out
    of point k (the point's `estimate.n` says how many scenarios were used)."""
    counts = to_counts(data)
    if not counts:
        return []
    kmax = min(MAX_K, max(n for _, n in counts))
    stats = [passk_stat(k) for k in range(1, kmax + 1)]
    boots = bootstrap_counts(counts, stats, resamples=resamples, seed=seed)
    points = []
    for k, stat, boot in zip(range(1, kmax + 1), stats, boots, strict=True):
        usable = [(c, n) for c, n in counts if n >= k]
        points.append(ReliabilityPoint(k, _estimate(usable, stat, boot)))
    return points
