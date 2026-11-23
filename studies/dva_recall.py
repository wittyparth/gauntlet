"""DVA recall and clean-control false positives (P2-9 script, scripted brain)."""

from __future__ import annotations

import sys

from dva.recall import AGENTS, run_recall

from .common import StudyResult, now, platform_version, run_cli, wilson


async def build(seed: int, smoke: bool) -> StudyResult:
    agents = ["sql"] if smoke else list(AGENTS)
    per_cat = 2 if smoke else 10
    metrics: dict[str, float] = {}
    intervals: dict[str, tuple[float, float]] = {}
    misses: list[str] = []
    total = 0
    for a in agents:
        r = await run_recall(a, per_category=per_cat, seed=seed)
        scope, found = len(r["flaws_in_scope"]), len(r["flaws_detected"])
        metrics[f"recall.{a}"] = r["recall"]
        intervals[f"recall.{a}"] = wilson(found, scope)
        metrics[f"false_positives_on_clean.{a}"] = float(r["false_positives_on_clean"])
        total += scope
        misses.append(
            f"{a}: undetected {r['undetected'] or 'none'}; expected misses "
            f"{r['expected_misses'] or 'none'}; {r['unmatched_findings']} unmatched findings"
        )
    return StudyResult(
        name="dva_recall", seed=seed, platform_version=platform_version(), started_at=now(),
        smoke=smoke, metrics=metrics, intervals=intervals, n=total,
        limitations=[
            "Scripted brain: measures the detection pipeline, not any model's vulnerability.",
            "Interval is Wilson over flaws in scope (the unit of recall), not over attacks.",
            "Flaws are known to us: recall is on a catalog we wrote, an optimistic upper bound.",
        ],
        notes="Miss analysis. " + " | ".join(misses),
    )  # fmt: skip


if __name__ == "__main__":
    sys.exit(run_cli("dva_recall", build))
