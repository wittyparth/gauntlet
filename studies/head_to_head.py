"""Optional head-to-head with other open-source scanners on the DVA, findings counted by flaw
id, same time and cost budget, pinned versions, licences respected.

Scanner adapters are not shipped (running third-party scanners is a manual task with pinned
installs). This study reads a results file `--scanners PATH`: `[{scanner, version, licence,
flaws_found: [ids], flaws_in_scope: n}]`. Without a file it writes an explicit not-run result
(n = 0) instead of inventing numbers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .common import StudyResult, now, platform_version, run_cli, wilson


async def build(seed: int, smoke: bool, scanners: Path | None = None) -> StudyResult:
    if scanners is None:
        return StudyResult(
            name="head_to_head", seed=seed, platform_version=platform_version(), started_at=now(),
            smoke=smoke, metrics={}, n=0,
            limitations=["Not run: no scanner results supplied (`--scanners PATH`)."],
            notes="No comparison is published until pinned scanners have been run by hand.",
        )  # fmt: skip
    rows = json.loads(scanners.read_text())
    metrics: dict[str, float] = {}
    intervals: dict[str, tuple[float, float]] = {}
    for r in rows:
        key = f"recall.{r['scanner']}@{r['version']}"
        found, scope = len(set(r["flaws_found"])), int(r["flaws_in_scope"])
        metrics[key] = found / scope if scope else 0.0
        intervals[key] = wilson(found, scope)
    return StudyResult(
        name="head_to_head", seed=seed, platform_version=platform_version(), started_at=now(),
        smoke=smoke, metrics=metrics, intervals=intervals, n=len(rows),
        limitations=[
            "The DVA catalog was written for this platform and favours it.",
            "Scanners differ in what they count as a finding; we map findings to flaw ids by hand.",
        ],
        notes="Licences: " + ", ".join(f"{r['scanner']} ({r['licence']})" for r in rows),
    )  # fmt: skip


if __name__ == "__main__":
    sys.exit(run_cli("head_to_head", build, extra={"scanners": Path}))
