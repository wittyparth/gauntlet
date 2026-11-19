"""Judge-versus-human agreement: accuracy, precision and recall on the fail class, kappa."""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

from .intervals import percentile


def cohens_kappa(a: Sequence[bool], b: Sequence[bool]) -> float:
    """Cohen's kappa for two binary raters. When chance agreement is 1 (both constant and
    equal) the value is 1.0 if they agree entirely, else 0.0."""
    if len(a) != len(b) or not a:
        raise ValueError("need two non-empty sequences of equal length")
    n = len(a)
    po = sum(1 for x, y in zip(a, b, strict=True) if x == y) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    if pe >= 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


@dataclass(frozen=True)
class Agreement:
    n: int
    accuracy: float
    precision: float | None  # None when the judge never predicted the fail class
    recall: float | None  # None when there are no true fails
    kappa: float
    kappa_low: float
    kappa_high: float


def judge_agreement(
    judge_fail: Sequence[bool],
    human_fail: Sequence[bool],
    *,
    resamples: int = 2000,
    seed: int = 0,
) -> Agreement:
    """`True` means the fail class. Human labels are the reference."""
    if len(judge_fail) != len(human_fail) or not judge_fail:
        raise ValueError("need two non-empty sequences of equal length")
    n = len(judge_fail)
    pairs = list(zip(judge_fail, human_fail, strict=True))
    tp = sum(1 for j, h in pairs if j and h)
    fp = sum(1 for j, h in pairs if j and not h)
    fn = sum(1 for j, h in pairs if not j and h)
    accuracy = sum(1 for j, h in pairs if j == h) / n
    kappa = cohens_kappa(judge_fail, human_fail)
    rng = random.Random(seed)
    boots = []
    for _ in range(resamples):
        sample = [pairs[rng.randrange(n)] for _ in range(n)]
        boots.append(cohens_kappa([j for j, _ in sample], [h for _, h in sample]))
    boots.sort()
    low, high = percentile(boots, 0.025), percentile(boots, 0.975)
    return Agreement(
        n=n,
        accuracy=accuracy,
        precision=tp / (tp + fp) if tp + fp else None,
        recall=tp / (tp + fn) if tp + fn else None,
        kappa=kappa,
        kappa_low=min(low, kappa),
        kappa_high=max(high, kappa),
    )
