"""Model migration report and Pareto data (P3-8). Everything is read from stored runs; the
statistics come from `compare_runs` and the run reports."""

from __future__ import annotations

from typing import Literal

from gauntlet_core.eval import (
    CompareReport,
    ParetoPoint,
    ParetoResult,
    RunData,
    compare_runs,
    pareto_frontier,
)
from gauntlet_core.eval.pareto import METRICS
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Episode, Run
from ..db.sec_models import Finding as FindingRow
from ..errors import ApiError
from .compare import _owned_run, findings_delta, run_data
from .posture import _observed

__all__ = ["MigrationReport", "ParetoOut", "VersionSummary", "migration_report", "pareto"]

Recommendation = Literal["safe_to_migrate", "review", "do_not_migrate"]
SEVERITIES = ("critical", "high", "medium", "low")


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VersionSummary(_M):
    agent_version_id: str
    label: str
    model: str | None
    pass_rate: float | None
    ci_low: float | None
    ci_high: float | None
    pass_hat_3: float | None
    open_findings_by_severity: dict[str, int]
    attack_success_rate: float | None
    cost_per_episode_usd_micros: int
    cost_per_1000_episodes_usd: float
    latency_p50_ms: int | None
    latency_p95_ms: int | None
    tokens_per_episode: int | None
    episodes: int


class MigrationReport(_M):
    compare: CompareReport
    baseline: VersionSummary
    candidate: VersionSummary
    recommendation: Recommendation
    reasons: list[str]
    cost_change_pct: float | None
    latency_p95_change_pct: float | None
    cautions: list[str]


class ParetoOut(_M):
    suite_id: str
    metrics: list[str]
    points: list[ParetoResult]
    cautions: list[str]


def _incomparable(a: RunData, b: RunData) -> list[str]:
    reasons = []
    if a.suite_id != b.suite_id:
        reasons.append(f"the runs use different suites ({a.suite_id} and {b.suite_id})")
    if a.scenario_versions != b.scenario_versions:
        changed = sorted(
            k
            for k in set(a.scenario_versions) | set(b.scenario_versions)
            if a.scenario_versions.get(k) != b.scenario_versions.get(k)
        )
        reasons.append(
            f"{len(changed)} scenario(s) differ in version or presence: " + ", ".join(changed[:5])
        )
    return reasons


async def _summary(s: AsyncSession, run: Run, data: RunData) -> VersionSummary:
    rep = data.report
    vid = run.agent_version_id
    open_rows = (
        await s.execute(
            select(FindingRow.severity, func.count())
            .where(
                FindingRow.workspace_id == run.workspace_id,
                FindingRow.agent_version_id == vid,
                FindingRow.status == "open",
            )
            .group_by(FindingRow.severity)
        )
    ).all()
    by = {sev: int(n) for sev, n in open_rows}
    observed = await _observed(s, vid)
    attempts = sum(a for a, _ in observed.values())
    wins = sum(k for _, k in observed.values())
    toks = (
        await s.execute(
            select(
                func.coalesce(func.sum(Episode.tokens_in), 0)
                + func.coalesce(func.sum(Episode.tokens_out), 0),
                func.count(),
            ).where(Episode.run_id == run.id, Episode.status == "done")
        )
    ).one()
    hat3 = next((p.value for p in rep.reliability if p.k == 3), None)
    return VersionSummary(
        agent_version_id=vid,
        label=data.agent_label,
        model=data.model,
        pass_rate=rep.pass_rate,
        ci_low=rep.ci_low,
        ci_high=rep.ci_high,
        pass_hat_3=hat3,
        open_findings_by_severity=by,
        attack_success_rate=wins / attempts if attempts else None,
        cost_per_episode_usd_micros=rep.cost_per_episode_usd_micros,
        cost_per_1000_episodes_usd=rep.cost_per_episode_usd_micros / 1000,
        latency_p50_ms=rep.latency_p50_ms,
        latency_p95_ms=rep.latency_p95_ms,
        tokens_per_episode=round(int(toks[0]) / int(toks[1]))
        if int(toks[1]) and int(toks[0])
        else None,
        episodes=rep.counted,
    )


def _new_hard_fail_scenarios(base: RunData, cand: RunData) -> list[str]:
    def scenarios(d: RunData) -> set[str]:
        by_ep = {r.episode_id: r.scenario_id for r in d.records}
        return {by_ep[e] for e in d.report.hard_fail_episodes if e in by_ep}

    return sorted(scenarios(cand) - scenarios(base))


def decide(
    *, blocking: bool, inconclusive: bool, newly_failing: bool, cost_up: bool
) -> Recommendation:
    """The recommendation rules (P3-8): blocking facts first, then the review triggers."""
    if blocking:
        return "do_not_migrate"
    if inconclusive or newly_failing or cost_up:
        return "review"
    return "safe_to_migrate"


def _pct(new: int | None, old: int | None) -> float | None:
    if new is None or not old:
        return None
    return (new - old) / old * 100


async def migration_report(
    s: AsyncSession, ws: str, run_id: str, baseline_id: str, force: bool
) -> MigrationReport:
    cand_run = await _owned_run(s, ws, run_id)
    base_run = await _owned_run(s, ws, baseline_id)
    if cand_run.status != "done" or base_run.status != "done":
        raise ApiError(409, "run_not_completed", "both runs must be completed")
    base, cand = await run_data(s, base_run), await run_data(s, cand_run)
    problems = _incomparable(base, cand)
    cautions: list[str] = []
    if problems:
        if not force:
            raise ApiError(422, "incomparable_runs", "; ".join(problems), {"reasons": problems})
        cautions.append(
            "Forced comparison of runs that are not like for like: " + "; ".join(problems)
        )
    cmp = compare_runs(base, cand)
    delta = await findings_delta(s, ws, run_id, baseline_id)
    new_hard = _new_hard_fail_scenarios(base, cand)
    newly_failing = [f.scenario_id for f in cmp.flips if f.status == "newly_failing"]
    cost_pct = cmp.cost.delta_pct
    cost_up = cmp.cost.run_per_episode_usd_micros > cmp.cost.baseline_per_episode_usd_micros

    reasons: list[str] = []
    blocking = False
    if cmp.verdict == "regression":
        blocking = True
        reasons.append(
            f"The comparison verdict is a regression (pass rate change {cmp.delta * 100:+.1f} "
            f"points, interval {cmp.ci_low * 100:+.1f} to {cmp.ci_high * 100:+.1f})."
        )
    crit = delta.new_by_severity.get("critical", 0)
    if crit:
        blocking = True
        reasons.append(f"{crit} new critical security finding(s) appear on the candidate.")
    if new_hard:
        blocking = True
        reasons.append(
            f"Hard-fail verdicts appear in {len(new_hard)} scenario(s) that had none: "
            + ", ".join(new_hard[:5])
            + "."
        )
    if cmp.verdict == "inconclusive":
        reasons.append("The comparison is inconclusive: there is too little data to decide.")
    if newly_failing:
        reasons.append(
            f"{len(newly_failing)} scenario(s) are newly failing: "
            + ", ".join(newly_failing[:5])
            + "."
        )
    if cost_up:
        reasons.append(
            "Cost per episode rose from "
            f"{cmp.cost.baseline_per_episode_usd_micros} to "
            f"{cmp.cost.run_per_episode_usd_micros} micro-USD"
            + (f" ({cost_pct:+.1f}%)." if cost_pct is not None else ".")
        )
    rec = decide(
        blocking=blocking, inconclusive=cmp.verdict == "inconclusive",
        newly_failing=bool(newly_failing), cost_up=cost_up,
    )  # fmt: skip
    if rec == "safe_to_migrate":
        reasons.append("No rule fired: no regression, no new critical finding, cost did not rise.")
    return MigrationReport(
        compare=cmp,
        baseline=await _summary(s, base_run, base),
        candidate=await _summary(s, cand_run, cand),
        recommendation=rec,
        reasons=reasons,
        cost_change_pct=cost_pct,
        latency_p95_change_pct=_pct(cmp.latency.p95_run_ms, cmp.latency.p95_baseline_ms),
        cautions=cautions,
    )


async def pareto(
    s: AsyncSession, ws: str, run_ids: list[str], metrics: list[str], force: bool
) -> ParetoOut:
    if not 2 <= len(run_ids) <= 8 or len(set(run_ids)) != len(run_ids):
        raise ApiError(422, "invalid_run_ids", "give 2 to 8 distinct run ids")
    bad = [m for m in metrics if m not in METRICS]
    if bad or not metrics:
        raise ApiError(422, "invalid_metrics", f"metrics must be a subset of {sorted(METRICS)}")
    runs = [await _owned_run(s, ws, r) for r in run_ids]
    if any(r.status != "done" for r in runs):
        raise ApiError(409, "run_not_completed", "all runs must be completed")
    cautions: list[str] = []
    if len({r.suite_id for r in runs}) > 1:
        if not force:
            raise ApiError(422, "incomparable_runs", "the runs use different suites")
        cautions.append("The runs use different suites; the comparison is not like for like.")
    datas: list[RunData] = [await run_data(s, r) for r in runs]
    points = [
        ParetoPoint(
            run_id=r.id,
            agent_version_id=r.agent_version_id,
            label=d.agent_label,
            model=d.model,
            pass_rate=d.report.pass_rate,
            ci_low=d.report.ci_low,
            ci_high=d.report.ci_high,
            cost_per_episode_usd_micros=d.report.cost_per_episode_usd_micros,
            latency_p95_ms=d.report.latency_p95_ms,
        )
        for r, d in zip(runs, datas, strict=True)
    ]
    if any(p.pass_rate is None for p in points):
        cautions.append("A run has no counted episodes; it can never dominate on pass rate.")
    return ParetoOut(
        suite_id=runs[0].suite_id,
        metrics=list(metrics),
        points=pareto_frontier(points, metrics),
        cautions=cautions,
    )
