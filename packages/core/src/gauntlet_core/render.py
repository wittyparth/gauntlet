"""Plain-text and markdown renderers for `RunReport` (the CLI adds Rich on top)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from gauntlet_core.eval.report import RunReport, ScenarioStats

__all__ = ["fmt_usd", "render_markdown", "render_text", "scenario_word"]


def fmt_usd(micros: int) -> str:
    return f"${micros / 1_000_000:.4f}"


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def scenario_word(s: ScenarioStats) -> str:
    if s.rate is None:
        return "N/A"
    return "PASS" if s.rate >= 1.0 else "FAIL" if s.rate <= 0.0 else "FLAKY"


def _interval(r: RunReport) -> str:
    if r.pass_rate is None:
        return "n/a"
    return f"{_pct(r.pass_rate)} (95% CI {_pct(r.ci_low)} to {_pct(r.ci_high)})"


def _summary_lines(r: RunReport, meta: Mapping[str, Any]) -> list[str]:
    lines = [f"Run: {r.run_id}"]
    for key, label in (
        ("pack", "Pack"),
        ("target", "Target"),
        ("suite", "Suite"),
        ("repetitions", "Repetitions"),
    ):
        if key in meta:
            lines.append(f"{label}: {meta[key]}")
    lines.append(f"Pass rate: {_interval(r)}")
    excl = ", ".join(f"{k}={v}" for k, v in sorted(r.excluded.items())) or "none"
    lines.append(f"Counted: {r.counted}; excluded: {excl}")
    lines.append(
        f"Cost: {fmt_usd(r.cost_usd_micros)} ({fmt_usd(r.cost_per_episode_usd_micros)} per episode)"
    )
    if "duration_s" in meta:
        lines.append(f"Duration: {meta['duration_s']:.1f}s")
    return lines


def _caution_lines(r: RunReport) -> list[str]:
    c, out = r.caution, []
    if c.self_preference:
        out.append("Judge and target share a model family; scores may favour the target.")
    if c.uncalibrated_rubrics:
        out.append("Uncalibrated rubrics (cannot gate CI): " + ", ".join(c.uncalibrated_rubrics))
    if c.world_fidelity == "simulated":
        out.append("Some tool results were simulated by a model (world fidelity reduced).")
    if c.reduced_coverage:
        out.append("Target is not wired: no world visibility, state checks have reduced coverage.")
    if c.unpriced_models:
        out.append("Unpriced models (cost understated): " + ", ".join(c.unpriced_models))
    return out


def render_text(r: RunReport, meta: Mapping[str, Any] | None = None) -> str:
    meta = meta or {}
    out = _summary_lines(r, meta)
    out += ["", "Scenarios:"]
    for s in r.per_scenario:
        out.append(
            f"  {s.scenario_id:<24} {s.passed}/{s.counted:<3} {_pct(s.rate):>5}  "
            f"{scenario_word(s)}  {s.title}"
        )
    if r.failures:
        out += ["", "Failures:"]
        out += [
            f"  {f.episode_id}  {f.scenario_id}  {', '.join(f.reasons) or '-'}" for f in r.failures
        ]
    if r.dimensions:
        out += ["", "Dimensions:"]
        for d in r.dimensions:
            out.append(
                f"  {d.criterion:<24} {_pct(d.score):>5}  pass={d.passed} fail={d.failed} "
                f"na={d.na} error={d.error}"
            )
    if cl := _caution_lines(r):
        out += ["", "Cautions:", *[f"  - {x}" for x in cl]]
    return "\n".join(out) + "\n"


def render_markdown(r: RunReport, meta: Mapping[str, Any] | None = None) -> str:
    meta = meta or {}
    out = [f"# Gauntlet run {r.run_id}", ""]
    out += [f"- {line}" for line in _summary_lines(r, meta)[1:]]
    out += ["", "## Scenarios", "", "| Scenario | Trials | Rate | Result |", "|---|---|---|---|"]
    for s in r.per_scenario:
        out.append(
            f"| {s.scenario_id}: {s.title} | {s.passed}/{s.counted} | {_pct(s.rate)} "
            f"| {scenario_word(s)} |"
        )
    if r.failures:
        out += ["", "## Failures", ""]
        out += [
            f"- `{f.episode_id}` ({f.scenario_id}): {', '.join(f.reasons) or '-'}"
            for f in r.failures
        ]
    if r.dimensions:
        out += [
            "",
            "## Dimensions",
            "",
            "| Criterion | Score | Pass | Fail | N/A | Error |",
            "|---|---|---|---|---|---|",
        ]
        out += [
            f"| {d.criterion} | {_pct(d.score)} | {d.passed} | {d.failed} | {d.na} | {d.error} |"
            for d in r.dimensions
        ]
    if cl := _caution_lines(r):
        out += ["", "## Cautions", "", *[f"- {x}" for x in cl]]
    return "\n".join(out) + "\n"
