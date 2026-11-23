"""Render the comparison table from result files. Published numbers are context: they are shown
as a pass or fail only for a comparable pair (same model), within 10 points on pass^1."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .harness import CONFIG, RESULTS, ReproResult, published_for

__all__ = ["TOLERANCE_POINTS", "render"]

TOLERANCE_POINTS = 10.0


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def _row(result: ReproResult, config: dict[str, Any]) -> str:
    p1 = next((p for p in result.passk if p.k == 1), None)
    cells = [result.suite, result.model, result.mode, str(result.trials)]
    cells.append(f"{_pct(p1.value)} ({_pct(p1.ci_low)} to {_pct(p1.ci_high)})" if p1 else "n/a")
    best = max(result.passk, key=lambda p: p.k, default=None)
    cells.append(f"k={best.k}: {_pct(best.value)}" if best and best.k > 1 else "n/a")
    pub = published_for(config, result.suite, result.model)  # the current config, not the run's
    comparable = [p for p in pub if p.get("comparable") and p.get("value") is not None]
    if comparable and p1:
        ref = float(comparable[0]["value"])
        gap = 100 * (p1.value - ref)
        verdict = "within" if abs(gap) <= TOLERANCE_POINTS else "outside, explain in writing"
        cells.append(
            f"{ref:.1f}% ({comparable[0].get('source', '?')}); gap {gap:+.1f} pts, {verdict}"
        )
    elif pub:
        cells.append("published number used a model we do not run; context only, no pass or fail")
    else:
        cells.append("no published number recorded")
    return "| " + " | ".join(cells) + " |"


def render(results_dir: Path = RESULTS, config_path: Path = CONFIG) -> str:
    results = [
        ReproResult.model_validate(json.loads(p.read_text()))
        for p in sorted(results_dir.glob("*.json"))
    ]
    config: dict[str, Any] = yaml.safe_load(config_path.read_text())
    lines = [
        "# Benchmark reproduction",
        "",
        "| Suite | Model | Mode | Trials | pass^1 (95% interval) | Highest k | Published |",
        "|---|---|---|---|---|---|---|",
        *(_row(r, config) for r in results),
        "",
    ]
    if not results:
        lines.append("No result files yet.")
    for r in results:
        lines += [f"## Deviations: {r.suite} on {r.model}", *(f"- {d}" for d in r.deviations), ""]
    lines.append(
        f"Acceptance for a comparable pair: within {TOLERANCE_POINTS:.0f} points absolute."
    )
    lines.append(f"Suites configured: {', '.join(sorted(config['suites']))}.")
    return "\n".join(lines) + "\n"
