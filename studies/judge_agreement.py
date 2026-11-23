"""Judge agreement with human labels per calibrated rubric (accuracy, fail-class precision and
recall, Cohen's kappa with interval, cascade cost per verdict, escalation rate).

Input is a labelled set file: a JSON list of `{rubric, human_fail, judge_fail, cost_usd_micros,
escalated}` rows (recorded judge outputs, so a run replays without a model). The hand-labelled
set of L-R3 is not committed yet: `--smoke` uses a small synthetic fixture and says so; a
full run needs `--labels PATH` and refuses without it."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from gauntlet_core.stats import judge_agreement

from .common import DATA_DIR, StudyResult, now, platform_version, run_cli, wilson

SMOKE_SET = DATA_DIR / "judge_labels_smoke.json"


def result_from_rows(rows: list[dict[str, Any]], seed: int, smoke: bool) -> StudyResult:
    metrics: dict[str, float] = {}
    intervals: dict[str, tuple[float, float]] = {}
    gaps: list[str] = []
    for rubric in sorted({r["rubric"] for r in rows}):
        sub = [r for r in rows if r["rubric"] == rubric]
        ag = judge_agreement(
            [bool(r["judge_fail"]) for r in sub], [bool(r["human_fail"]) for r in sub], seed=seed
        )
        correct = sum(1 for r in sub if bool(r["judge_fail"]) == bool(r["human_fail"]))
        metrics[f"accuracy.{rubric}"] = ag.accuracy
        intervals[f"accuracy.{rubric}"] = wilson(correct, ag.n)
        metrics[f"kappa.{rubric}"] = ag.kappa
        intervals[f"kappa.{rubric}"] = (ag.kappa_low, ag.kappa_high)
        for k, v in (("precision_fail", ag.precision), ("recall_fail", ag.recall)):
            if v is None:
                gaps.append(f"{k}.{rubric} undefined (no predictions or no true fails)")
            else:
                metrics[f"{k}.{rubric}"] = v
        metrics[f"cost_per_verdict_usd_micros.{rubric}"] = sum(
            r.get("cost_usd_micros", 0) for r in sub
        ) / len(sub)
        esc = sum(1 for r in sub if r.get("escalated"))
        metrics[f"escalation_rate.{rubric}"] = esc / len(sub)
        intervals[f"escalation_rate.{rubric}"] = wilson(esc, len(sub))
    return StudyResult(
        name="judge_agreement", seed=seed, platform_version=platform_version(),
        started_at=now(), smoke=smoke, metrics=metrics, intervals=intervals, n=len(rows),
        limitations=[
            "Human labels are the reference and carry their own noise.",
            "Precision and recall are point values (no interval); kappa has a bootstrap interval.",
            *(["SMOKE: synthetic fixture, not the hand-labelled set of L-R3."] if smoke else []),
        ],
        notes="; ".join(gaps),
    )  # fmt: skip


async def build(seed: int, smoke: bool, labels: Path | None = None) -> StudyResult:
    path = labels or (SMOKE_SET if smoke else None)
    if path is None:
        raise SystemExit("judge_agreement needs --labels PATH (the hand-labelled set) or --smoke")
    return result_from_rows(json.loads(path.read_text()), seed, smoke)


if __name__ == "__main__":
    sys.exit(run_cli("judge_agreement", build, extra={"labels": Path}))
