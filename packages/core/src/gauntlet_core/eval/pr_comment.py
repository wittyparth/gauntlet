"""The pull request comment (P3-4). ASCII only, first line is the marker the upsert script
looks for, hard size cap with list rows dropped first."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from gauntlet_core.gates import GateResult

from .compare import CompareReport
from .report import RunReport

__all__ = ["MARKER", "FindingBrief", "render_pr_comment"]

MARKER = "<!-- gauntlet-report -->"
MAX_FAILING = 10
MAX_FINDINGS = 5


@dataclass(frozen=True)
class FindingBrief:
    title: str
    severity: str
    category: str = ""


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def _usd(micros: int) -> str:
    return f"${micros / 1_000_000:.4f}"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").replace("<", "&lt;")


def _verdict_sentence(c: CompareReport) -> str:
    pts = f"{c.delta * 100:+.1f} points (95% CI {c.ci_low * 100:+.1f} to {c.ci_high * 100:+.1f})"
    if c.verdict == "regression":
        return f"Regression versus baseline: pass rate {pts}."
    if c.verdict == "improvement":
        return f"Improvement versus baseline: pass rate {pts}."
    if c.verdict == "inconclusive":
        extra = f" {c.detectable_effect_text}" if c.detectable_effect_text else ""
        return f"Inconclusive versus baseline: pass rate {pts}.{extra}"
    return f"No detectable change versus baseline: pass rate {pts}."


def _body(
    report: RunReport,
    compare: CompareReport | None,
    gate: GateResult,
    run_url: str,
    findings: Sequence[FindingBrief],
    n_failing: int,
    n_findings: int,
    gate_json: str,
) -> str:
    lines = [MARKER, f"## Gauntlet: {gate.status.upper()}", ""]
    rate = (
        "n/a"
        if report.pass_rate is None
        else f"{_pct(report.pass_rate)} (95% CI {_pct(report.ci_low)} to {_pct(report.ci_high)})"
    )
    rows = [("Pass rate", rate), ("Episodes counted", str(report.counted))]
    if compare is not None:
        rows.append(("Versus baseline", _verdict_sentence(compare)))
    k3 = next((p for p in report.reliability if p.k == 3), None)
    if k3 is not None:
        rows.append(
            ("pass^3", f"{_pct(k3.value)} (95% CI {_pct(k3.ci_low)} to {_pct(k3.ci_high)})")
        )
    cost = _usd(report.cost_per_episode_usd_micros)
    if compare is not None and compare.cost.delta_pct is not None:
        cost += f" ({compare.cost.delta_pct:+.1f}% versus baseline)"
    rows.append(("Cost per episode", cost))
    rows.append(
        (
            "Latency p95",
            "n/a" if report.latency_p95_ms is None else f"{report.latency_p95_ms} ms",
        )
    )
    cal = [d for d in report.dimensions if d.gating_allowed and d.score is not None]
    if cal:
        rows.append(
            ("Calibrated dimensions", ", ".join(f"{d.criterion} {_pct(d.score)}" for d in cal))
        )
    lines += ["| Metric | Value |", "|---|---|"]
    lines += [f"| {k} | {_cell(v)} |" for k, v in rows]

    newly = [f for f in (compare.flips if compare else []) if f.status == "newly_failing"]
    if newly:
        lines += ["", f"### Newly failing scenarios ({len(newly)})", ""]
        for f in newly[:n_failing]:
            link = f" ([episode]({run_url}/episodes/{f.episode_run}))" if f.episode_run else ""
            lines.append(
                f"- `{f.scenario_id}` {_cell(f.title)}: {_pct(f.rate_baseline)} to "
                f"{_pct(f.rate_run)}{link}"
            )
        if len(newly) > n_failing:
            lines.append(f"- ... and {len(newly) - n_failing} more (truncated)")
    if findings:
        lines += ["", f"### New security findings ({len(findings)})", ""]
        for f in findings[:n_findings]:
            lines.append(f"- {f.severity}: {_cell(f.title)}")
        if len(findings) > n_findings:
            lines.append(f"- ... and {len(findings) - n_findings} more (truncated)")

    lines += ["", "### Gates", "", "| Gate | Status | Detail |", "|---|---|---|"]
    for g in gate.gates:
        det = g.detail
        if g.value is not None and g.threshold is not None:
            val = f"{g.value:.3g}" if isinstance(g.value, float) else str(g.value)
            thr = f"{g.threshold:.3g}" if isinstance(g.threshold, float) else str(g.threshold)
            det = f"{val} against {thr}" + (f"; {det}" if det else "")
        elif g.value is not None:
            det = f"{g.value}" + (f"; {det}" if det else "")
        lines.append(f"| {g.id} | {g.status} | {_cell(det)} |")

    lines += ["", f"[View the full run]({run_url})", ""]
    lines += ["<details><summary>Gate result JSON</summary>", "", "```json", gate_json, "```", ""]
    lines += ["</details>", ""]
    return "\n".join(lines)


def render_pr_comment(
    report: RunReport,
    compare: CompareReport | None,
    gate: GateResult,
    run_url: str,
    *,
    max_chars: int = 60000,
    findings: Sequence[FindingBrief] = (),
) -> str:
    """Truncation order: list rows (newly failing, findings) shrink to zero, then the JSON
    block is cut. The result is always well-formed markdown no longer than `max_chars`."""
    full_json = gate.model_dump_json(indent=2).replace("```", "'''")
    attempts = [(MAX_FAILING, MAX_FINDINGS), (3, 2), (0, 0)]
    out = ""
    for nf, nsec in attempts:
        out = _body(report, compare, gate, run_url, findings, nf, nsec, full_json)
        if len(out) <= max_chars:
            return out
    overflow = len(out) - max_chars
    keep = max(0, len(full_json) - overflow - 40)
    cut = full_json[:keep] + "\n... (truncated)"
    out = _body(report, compare, gate, run_url, findings, 0, 0, cut)
    if len(out) > max_chars:  # pathological: even the table does not fit; drop the JSON block
        out = _body(report, compare, gate, run_url, findings, 0, 0, "(truncated)")
    return out[:max_chars] if len(out) > max_chars else out
