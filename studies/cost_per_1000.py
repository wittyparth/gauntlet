"""Cost per 1,000 episodes from run ledgers: a JSON list of `{episode_id, cost_usd_micros}`
(`--ledger PATH`, exported from real runs). Smoke derives rows from a scripted campaign, which
spends nothing, and says so."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dva.recall import run_recall

from .common import StudyResult, bootstrap_mean, now, platform_version, run_cli


async def build(seed: int, smoke: bool, ledger: Path | None = None) -> StudyResult:
    if ledger is not None:
        costs = [float(r["cost_usd_micros"]) for r in json.loads(ledger.read_text())]
    elif smoke:
        r = await run_recall("sql", per_category=2, seed=seed, control=False)
        costs = [float(a.get("cost_usd_micros") or 0) for a in r["attack_rows"]]
    else:
        raise SystemExit("cost_per_1000 needs --ledger PATH (exported run ledgers) or --smoke")
    mean, lo, hi = bootstrap_mean(costs, seed=seed)
    return StudyResult(
        name="cost_per_1000", seed=seed, platform_version=platform_version(), started_at=now(),
        smoke=smoke,
        metrics={"cost_per_1000_episodes_usd_micros": mean * 1000},
        intervals={"cost_per_1000_episodes_usd_micros": (lo * 1000, hi * 1000)},
        n=len(costs),
        limitations=[
            "Cost depends on the model, prompts and scenario mix of the ledgers supplied.",
            *(["SMOKE: scripted campaign, zero spend by construction."] if smoke else []),
        ],
    )  # fmt: skip


if __name__ == "__main__":
    sys.exit(run_cli("cost_per_1000", build, extra={"ledger": Path}))
