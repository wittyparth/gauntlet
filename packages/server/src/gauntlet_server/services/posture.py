"""Gathers the facts of a security posture report (P2-6) and applies the core scoring."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from gauntlet_core.schema import Event, Scenario, WorldSpec
from gauntlet_core.security.posture import (
    ComplianceRow,
    CoverageCell,
    FindingFact,
    Grade,
    Recommendation,
    ToolReview,
    compliance,
    coverage_cells,
    coverage_fraction,
    grade,
    recommendations,
    tool_review,
    tool_usage,
)
from gauntlet_core.validate import walk_check
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import models as m
from ..db.sec_models import EpisodeAttack, FindingEpisode
from ..db.sec_models import Finding as FindingRow
from ..errors import not_found
from .attack_lib import taxonomy

__all__ = ["PostureOut", "build_coverage", "build_posture"]


class PostureFinding(BaseModel):
    id: str
    title: str
    category: str
    severity: str
    status: str
    reproducibility: tuple[int, int]


class Summary(BaseModel):
    open_by_severity: dict[str, int]
    verified: int
    accepted_risk: int
    attacks_run: int
    attack_success_rate: float


class DataExposure(BaseModel):
    canary_id: str
    kind: str
    placement: str
    planted_episodes: int
    leaked_episodes: int


class Previous(BaseModel):
    version_id: str
    grade: str
    new: int
    fixed: int
    unchanged: int


class PostureOut(BaseModel):
    agent_version_id: str
    generated_at: str
    grade: str
    grade_basis: list[str]
    summary: Summary
    coverage: list[CoverageCell]
    top_findings: list[PostureFinding]
    tool_review: list[ToolReview]
    data_exposure: list[DataExposure]
    previous: Previous | None
    recommendations: list[Recommendation]
    compliance: list[ComplianceRow]


class CoverageOut(BaseModel):
    agent_version_id: str
    coverage: list[CoverageCell]


async def _version(s: AsyncSession, ws: str, agent_id: str, vid: str) -> m.AgentVersion:
    av = await s.get(m.AgentVersion, vid)
    if av is None or av.workspace_id != ws or av.agent_id != agent_id:
        raise not_found("agent version", vid)
    return av


async def _observed(s: AsyncSession, vid: str) -> dict[tuple[str, str], tuple[int, int]]:
    rows = (
        await s.execute(
            select(
                EpisodeAttack.category,
                EpisodeAttack.vector,
                func.count(),
                func.count().filter(EpisodeAttack.objective_held.is_(True)),
            )
            .join(m.Episode, m.Episode.id == EpisodeAttack.episode_id)
            .join(m.Run, m.Run.id == m.Episode.run_id)
            .where(m.Run.agent_version_id == vid, m.Episode.outcome.in_(("passed", "failed")))
            .group_by(EpisodeAttack.category, EpisodeAttack.vector)
        )
    ).all()
    return {(c, v): (int(a), int(k)) for c, v, a, k in rows}


async def build_coverage(s: AsyncSession, ws: str, agent_id: str, vid: str) -> dict[str, Any]:
    await _version(s, ws, agent_id, vid)
    cells = coverage_cells(taxonomy(), await _observed(s, vid))
    return {"agent_version_id": vid, "coverage": cells}


async def _world(s: AsyncSession, ws: str, av: m.AgentVersion) -> WorldSpec | None:
    if not av.world_id:
        return None
    row = (
        await s.execute(
            select(m.World)
            .where(m.World.workspace_id == ws, m.World.id == av.world_id)
            .order_by(m.World.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return WorldSpec.model_validate(row.doc) if row else None


async def _facts(
    s: AsyncSession, rows: list[FindingRow], risk: dict[str, str]
) -> list[FindingFact]:
    facts = []
    for r in rows:
        links = (
            (await s.execute(select(FindingEpisode).where(FindingEpisode.finding_id == r.id)))
            .scalars()
            .all()
        )
        tools: list[str] = []
        for ln in links:
            if not ln.evidence_seqs:
                continue
            evs = (
                await s.execute(
                    select(m.Event).where(
                        m.Event.episode_id == ln.episode_id, m.Event.seq.in_(ln.evidence_seqs)
                    )
                )
            ).scalars()
            for e in evs:
                if e.kind == "tool_call":
                    t = str(e.doc.get("payload", {}).get("tool"))
                    label = f"{t}:{risk.get(t, 'read')}"
                    if label not in tools:
                        tools.append(label)
        facts.append(
            FindingFact(
                id=r.id, title=r.title, category=r.category, severity=r.severity,  # type: ignore[arg-type]
                status=r.status, reproducibility=(r.repro_successes, r.repro_attempts),
                dedup_key=r.dedup_key, tools=tools,
            )
        )  # fmt: skip
    return facts


async def _findings(s: AsyncSession, ws: str, vid: str) -> list[FindingRow]:
    q = select(FindingRow).where(FindingRow.workspace_id == ws, FindingRow.agent_version_id == vid)
    return list((await s.execute(q.order_by(FindingRow.created_at))).scalars())


async def _episode_rows(s: AsyncSession, vid: str) -> list[tuple[str, bool, dict[str, Any]]]:
    rows = (
        await s.execute(
            select(EpisodeAttack.episode_id, EpisodeAttack.objective_held, m.Scenario.doc)
            .join(m.Episode, m.Episode.id == EpisodeAttack.episode_id)
            .join(m.Run, m.Run.id == m.Episode.run_id)
            .join(
                m.Scenario,
                (m.Scenario.id == m.Episode.scenario_id)
                & (m.Scenario.version == m.Episode.scenario_version),
            )
            .where(m.Run.agent_version_id == vid, m.Episode.outcome.in_(("passed", "failed")))
        )
    ).all()
    return [(e, bool(h), d) for e, h, d in rows]


def _leaked(scn: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for nc in Scenario.model_validate(scn).forbidden:
        if nc.id == "objective":
            for n in walk_check(nc.check):
                if n.type == "canary_leaked":
                    out.add(n.canary)
    return out


async def build_posture(
    s: AsyncSession, ws: str, agent_id: str, vid: str, compare_to: str | None = None
) -> dict[str, Any]:
    av = await _version(s, ws, agent_id, vid)
    tax = taxonomy()
    world = await _world(s, ws, av)
    risk = {t.name: t.risk for t in world.tools} if world else {}
    cells = coverage_cells(tax, await _observed(s, vid))
    cov = coverage_fraction(tax, cells)
    rows = await _findings(s, ws, vid)
    facts = await _facts(s, rows, risk)
    g: Grade = grade(facts, cov)

    ep_rows = await _episode_rows(s, vid)
    usage: dict[str, tuple[int, int]] = {}
    for eid, _, _ in ep_rows:
        evs = (
            (
                await s.execute(
                    select(m.Event).where(m.Event.episode_id == eid).order_by(m.Event.seq)
                )
            )
            .scalars()
            .all()
        )
        for tool, (c, t) in tool_usage([Event.model_validate(e.doc) for e in evs]).items():
            c0, t0 = usage.get(tool, (0, 0))
            usage[tool] = (c0 + c, t0 + t)
    honey = [t.name for t in world.tools if t.honeytool] if world else []
    exposure = []
    if world:
        leaks = [(h, _leaked(d)) for _, h, d in ep_rows]
        for c in world.canaries:
            exposure.append(
                DataExposure(
                    canary_id=c.id, kind=c.kind, placement=c.placement,
                    planted_episodes=len(ep_rows),
                    leaked_episodes=sum(1 for h, ids in leaks if h and (c.id in ids or "*" in ids)),
                )
            )  # fmt: skip

    open_by: dict[str, int] = {}
    for f in facts:
        if f.is_open:
            open_by[f.severity] = open_by.get(f.severity, 0) + 1
    attempts = sum(c.attempts for c in cells)
    wins = sum(c.successes for c in cells)
    order = {"critical": 3, "high": 2, "medium": 1, "low": 0}
    top = sorted(facts, key=lambda f: (not f.is_open, -order[f.severity], -f.rate, f.id))[:10]
    return {
        "agent_version_id": vid,
        "generated_at": datetime.now(UTC).isoformat(),
        "grade": g.letter,
        "grade_basis": g.basis,
        "summary": {
            "open_by_severity": open_by,
            "verified": sum(1 for f in facts if f.status == "verified"),
            "accepted_risk": sum(1 for f in facts if f.status == "accepted_risk"),
            "attacks_run": attempts,
            "attack_success_rate": wins / attempts if attempts else 0.0,
        },
        "coverage": cells,
        "top_findings": [
            PostureFinding(**f.model_dump(include=set(PostureFinding.model_fields))) for f in top
        ],
        "tool_review": tool_review(risk, usage, honey),
        "data_exposure": exposure,
        "previous": await _previous(s, ws, av, compare_to, facts, cov),
        "recommendations": recommendations(facts),
        "compliance": compliance(tax, cells, facts),
    }


async def _previous(
    s: AsyncSession, ws: str, av: m.AgentVersion, compare_to: str | None,
    facts: list[FindingFact], cov: float,
) -> Previous | None:  # fmt: skip
    if compare_to:
        prev = await s.get(m.AgentVersion, compare_to)
        if prev is None or prev.workspace_id != ws:
            raise not_found("agent version", compare_to)
    else:
        prev = (
            await s.execute(
                select(m.AgentVersion)
                .where(
                    m.AgentVersion.agent_id == av.agent_id,
                    m.AgentVersion.workspace_id == ws,
                    m.AgentVersion.created_at < av.created_at,
                )
                .order_by(m.AgentVersion.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    if prev is None:
        return None
    pworld = await _world(s, ws, prev)
    prisk = {t.name: t.risk for t in pworld.tools} if pworld else {}
    pfacts = await _facts(s, await _findings(s, ws, prev.id), prisk)
    pcells = coverage_cells(taxonomy(), await _observed(s, prev.id))
    cur, old = {f.dedup_key for f in facts}, {f.dedup_key for f in pfacts}
    return Previous(
        version_id=prev.id,
        grade=grade(pfacts, coverage_fraction(taxonomy(), pcells)).letter,
        new=len(cur - old), fixed=len(old - cur), unchanged=len(cur & old),
    )  # fmt: skip
