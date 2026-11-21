"""Rich rendering of a `RunReport` for the terminal (plain renderers live in core)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from gauntlet_core.eval import RunReport
from gauntlet_core.render import fmt_usd, scenario_word
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

__all__ = ["print_report"]

_STYLE = {"PASS": "green", "FAIL": "red", "FLAKY": "yellow", "N/A": "dim"}


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def print_report(report: RunReport, meta: Mapping[str, Any], console: Console) -> None:
    excl = ", ".join(f"{k} {v}" for k, v in sorted(report.excluded.items())) or "none"
    rate = (
        "n/a"
        if report.pass_rate is None
        else f"{_pct(report.pass_rate)} (95% CI {_pct(report.ci_low)} to {_pct(report.ci_high)})"
    )
    lines = [f"[bold]Pass rate[/bold]  {rate}"]
    for key, label in (("pack", "Pack"), ("target", "Target"), ("suite", "Suite"),
                       ("repetitions", "Repetitions")):  # fmt: skip
        if key in meta:
            lines.append(f"[bold]{label}[/bold]  {meta[key]}")
    lines.append(f"[bold]Episodes[/bold]  counted {report.counted}, excluded: {excl}")
    cost = (
        f"{fmt_usd(report.cost_usd_micros)} ({fmt_usd(report.cost_per_episode_usd_micros)}/episode)"
    )
    lines.append(f"[bold]Cost[/bold]  {cost}")
    if "duration_s" in meta:
        lines.append(f"[bold]Duration[/bold]  {meta['duration_s']:.1f}s")
    console.print(Panel("\n".join(lines), title=f"Gauntlet run {report.run_id}", expand=False))

    table = Table(title="Scenarios")
    for col in ("Scenario", "Title", "Trials", "Rate", "Result"):
        table.add_column(col)
    for s in report.per_scenario:
        word = scenario_word(s)
        table.add_row(
            s.scenario_id, s.title, f"{s.passed}/{s.counted}", _pct(s.rate),
            f"[{_STYLE[word]}]{word}[/{_STYLE[word]}]",
        )  # fmt: skip
    console.print(table)

    if len(report.reliability) > 1:
        rel = Table(title="Reliability (pass^k: all k repetitions pass)")
        for col in ("k", "pass^k", "95% CI", "Scenarios"):
            rel.add_column(col)
        for p in report.reliability:
            rel.add_row(f"{p.k}", _pct(p.value), f"{_pct(p.ci_low)} to {_pct(p.ci_high)}",
                        f"{p.scenarios}")  # fmt: skip
        console.print(rel)
    elif report.reliability:
        console.print("[dim]Reliability: increase repetitions to see reliability (pass^k).[/dim]")
    flaky = [s.scenario_id for s in report.per_scenario if s.flaky]
    if flaky:
        console.print("[yellow]Flaky scenarios:[/yellow] " + ", ".join(flaky))
    if report.failures:
        console.print("[bold]Failures[/bold]")
        for f in report.failures:
            console.print(f"  {f.episode_id}  {f.scenario_id}  {', '.join(f.reasons) or '-'}")
    if report.dimensions:
        dims = Table(title="Dimensions")
        for col in ("Criterion", "Score", "Pass", "Fail", "N/A", "Error"):
            dims.add_column(col)
        for d in report.dimensions:
            dims.add_row(d.criterion, _pct(d.score), str(d.passed), str(d.failed), str(d.na),
                         str(d.error))  # fmt: skip
        console.print(dims)
    c = report.caution
    notes = []
    if c.self_preference:
        notes.append("Judge and target share a model family; scores may favour the target.")
    if c.uncalibrated_rubrics:
        notes.append("Uncalibrated rubrics (cannot gate CI): " + ", ".join(c.uncalibrated_rubrics))
    if c.world_fidelity == "simulated":
        notes.append("Some tool results were simulated by a model.")
    if c.reduced_coverage:
        notes.append("Target is not wired: reduced world coverage.")
    if c.adaptive_sampling:
        notes.append("Adaptive sampling: early-stopped scenarios report posterior means.")
    if report.quarantined:
        notes.append("Quarantined (excluded from the pass rate): " + ", ".join(report.quarantined))
    if c.unpriced_models:
        notes.append("Unpriced models (cost understated): " + ", ".join(c.unpriced_models))
    for n in notes:
        console.print(f"[yellow]Caution:[/yellow] {n}")
