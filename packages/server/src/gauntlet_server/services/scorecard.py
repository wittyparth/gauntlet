"""Agent version scorecard (P3-8): one page of stored facts, nothing recomputed with a model."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from gauntlet_core.eval import RunReport
from gauntlet_core.eval.reliability import ReliabilityPoint
from gauntlet_core.security.posture import coverage_cells, coverage_fraction
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api_models import AgentVersionOut
from ..db.models import Run
from ..db.review_models import BadgeToken
from .attack_lib import taxonomy
from .posture import _observed, _version, build_posture
from .reports import run_report

__all__ = ["Scorecard", "build_scorecard"]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LatestRun(_M):
    id: str
    finished_at: str | None
    pass_rate: float | None
    ci_low: float | None
    ci_high: float | None
    pass_hat_k: list[ReliabilityPoint]
    counted: int


class Dimension(_M):
    criterion: str
    score: float | None
    severity: Literal["low", "medium", "high", "critical"]
    gating_allowed: bool


class SecuritySummary(_M):
    grade: str
    open_findings_by_severity: dict[str, int]
    coverage_pct: float


class TrendPoint(_M):
    run_id: str
    finished_at: str | None
    pass_rate: float | None


class BadgeLink(_M):
    url: str
    markdown: str


class ScorecardData(_M):
    latest_run: LatestRun | None
    dimensions: list[Dimension]
    security: SecuritySummary | None
    cost_per_1000_episodes_usd: float | None
    latency_p95_ms: int | None
    quarantined_scenarios: int
    trend: list[TrendPoint]
    badge: BadgeLink | None
    generated_at: str
    caveats: list[str]


class Scorecard(ScorecardData):
    agent_version: AgentVersionOut


async def build_scorecard(
    s: AsyncSession, ws: str, agent_id: str, vid: str, public_url: str
) -> ScorecardData:
    await _version(s, ws, agent_id, vid)
    runs = (
        (
            await s.execute(
                select(Run)
                .where(
                    Run.workspace_id == ws,
                    Run.agent_version_id == vid,
                    Run.status == "done",
                    Run.purpose == "eval",
                )
                .order_by(Run.finished_at.desc().nulls_last(), Run.id.desc())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )
    caveats: list[str] = []
    latest: LatestRun | None = None
    dims: list[Dimension] = []
    cost = p95 = None
    quarantined = 0
    trend: list[TrendPoint] = []
    rep: RunReport | None = None
    reports: list[tuple[Run, RunReport]] = [(r, await run_report(s, r)) for r in runs]
    if reports:
        run, rep = reports[0]
        latest = LatestRun(
            id=run.id,
            finished_at=run.finished_at.isoformat() if run.finished_at else None,
            pass_rate=rep.pass_rate,
            ci_low=rep.ci_low,
            ci_high=rep.ci_high,
            pass_hat_k=list(rep.reliability),
            counted=rep.counted,
        )
        dims = [
            Dimension(
                criterion=d.criterion, score=d.score, severity=d.severity,
                gating_allowed=d.gating_allowed,
            )
            for d in rep.dimensions
        ]  # fmt: skip
        cost = rep.cost_per_episode_usd_micros / 1000
        p95 = rep.latency_p95_ms
        quarantined = len(rep.quarantined)
        trend = [
            TrendPoint(
                run_id=r.id,
                finished_at=r.finished_at.isoformat() if r.finished_at else None,
                pass_rate=rp.pass_rate,
            )
            for r, rp in reversed(reports)
        ]
        if rep.caution.uncalibrated_rubrics:
            caveats.append(
                "Uncalibrated rubrics: " + ", ".join(rep.caution.uncalibrated_rubrics) + "."
            )
        if run.repetitions < 3:
            caveats.append("Fewer than 3 repetitions per scenario: pass^k is not meaningful.")
        if rep.caution.adaptive_sampling:
            caveats.append("Adaptive sampling was used: scenarios stopped early once decided.")
        if rep.caution.self_preference:
            caveats.append("The judge and the agent share a model family (self-preference risk).")
        if rep.caution.reduced_coverage:
            caveats.append("The target kind gives reduced coverage of the scenario checks.")
    else:
        caveats.append("No completed evaluation run for this version.")

    security: SecuritySummary | None = None
    observed = await _observed(s, vid)
    if observed:
        posture = await build_posture(s, ws, agent_id, vid)
        cells = coverage_cells(taxonomy(), observed)
        security = SecuritySummary(
            grade=str(posture["grade"]),
            open_findings_by_severity=dict(posture["summary"]["open_by_severity"]),
            coverage_pct=round(coverage_fraction(taxonomy(), cells) * 100, 1),
        )
    else:
        caveats.append("No security run for this version: no grade is shown.")

    token = (
        await s.execute(
            select(BadgeToken.token)
            .where(BadgeToken.agent_id == agent_id, BadgeToken.revoked_at.is_(None))
            .order_by(BadgeToken.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    badge = None
    if token:
        url = f"{public_url.rstrip('/')}/badge/{token}.svg"
        badge = BadgeLink(url=url, markdown=f"![gauntlet]({url})")
    return ScorecardData(
        latest_run=latest,
        dimensions=dims,
        security=security,
        cost_per_1000_episodes_usd=cost,
        latency_p95_ms=p95,
        quarantined_scenarios=quarantined,
        trend=trend,
        badge=badge,
        generated_at=datetime.now(UTC).isoformat(),
        caveats=caveats,
    )
