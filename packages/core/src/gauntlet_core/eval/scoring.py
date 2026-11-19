"""Dimension and composite scores from rubric verdicts. Pure functions."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from gauntlet_core.schema import Verdict

__all__ = ["SEVERITY_WEIGHT", "composite_score", "dimension_score", "hard_fail_episodes"]

SEVERITY_WEIGHT: dict[str, int] = {"low": 1, "medium": 2, "high": 4, "critical": 8}


def dimension_score(passed: int, failed: int) -> float | None:
    """passed / (passed + failed); `na` and `error` verdicts are not part of it."""
    n = passed + failed
    return passed / n if n else None


def composite_score(dimensions: Iterable[tuple[float | None, str]]) -> float | None:
    """Severity-weighted mean of the dimension scores that exist."""
    num = den = 0.0
    for score, severity in dimensions:
        if score is None:
            continue
        w = SEVERITY_WEIGHT[severity]
        num += w * score
        den += w
    return num / den if den else None


def hard_fail_episodes(verdicts: dict[str, Sequence[Verdict]]) -> list[str]:
    return sorted(
        ep for ep, vs in verdicts.items() if any(v.result == "fail" and v.hard_fail for v in vs)
    )
