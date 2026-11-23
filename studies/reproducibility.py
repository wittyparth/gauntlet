"""Reproducibility: one suite, one agent, five reruns. Variance of the attack-success rate with
an interval, and whether every rerun's per-attack rows are identical (strict replay)."""

from __future__ import annotations

import sys

from dva.recall import run_recall

from .common import StudyResult, now, platform_version, run_cli, wilson

RERUNS = 5


async def build(seed: int, smoke: bool) -> StudyResult:
    per_cat = 2 if smoke else 10
    runs = [
        await run_recall("sql", per_category=per_cat, seed=seed, control=False)
        for _ in range(RERUNS)
    ]
    rows = [r["attack_rows"] for r in runs]
    identical = all(x == rows[0] for x in rows)
    rates = [sum(1 for a in rr if not a["held"]) / len(rr) if rr else 0.0 for rr in rows]
    mean = sum(rates) / len(rates)
    var = sum((x - mean) ** 2 for x in rates) / (len(rates) - 1)
    pooled = sum(sum(1 for a in rr if not a["held"]) for rr in rows)
    total = sum(len(rr) for rr in rows)
    return StudyResult(
        name="reproducibility", seed=seed, platform_version=platform_version(),
        started_at=now(), smoke=smoke,
        metrics={
            "attack_success_rate": pooled / total if total else 0.0,
            "attack_success_rate_variance": var,
            "replay_identical": 1.0 if identical else 0.0,
        },
        intervals={"attack_success_rate": wilson(pooled, total)},
        n=total,
        limitations=[
            "Scripted brain with a fixed seed: variance reflects the platform, not a model.",
            "Interval pools the five reruns as if independent, which they are not when replay is "
            "identical; read it as an upper bound on uncertainty.",
        ],
        notes=f"{RERUNS} reruns on the sql DVA agent.",
    )  # fmt: skip


if __name__ == "__main__":
    sys.exit(run_cli("reproducibility", build))
