"""Change impact over stored scenarios and history (P5-7): which scenarios to re-run after a
change between two agent versions (and optionally two policy versions). The selection itself is
`gauntlet_core.impact.compute_impact`; this module builds its inputs from the database."""

from __future__ import annotations

from typing import Any

from gauntlet_core.impact import (
    ImpactHistory,
    ScenarioInfo,
    classify_change,
    compute_impact,
)
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import models as m
from ..db.policy_models import PolicyVersion
from ..errors import ApiError, not_found

__all__ = ["ChangeOut", "ImpactIn", "ImpactOut", "SuggestedSuite", "impact_for_versions"]

RISKS = {"high", "medium", "low"}
FLIP_RUNS = 5


class ImpactIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_version: str
    to_version: str
    policy_from: str | None = None  # a policy id or `id@version`
    policy_to: str | None = None


class ChangeOut(BaseModel):
    tools: list[str]
    policy_clauses: list[str]
    model: bool
    prompt: bool
    worlds: list[str]
    unknown: bool


class SuggestedSuite(BaseModel):
    name: str
    scenario_ids: list[str]


class ImpactOut(BaseModel):
    change: ChangeOut
    scenario_ids: list[str]
    reasons: dict[str, list[str]]
    full_run: bool
    total_scenarios: int
    suggested_suite: SuggestedSuite


def _tools_in(check: Any) -> set[str]:
    """Every `tool` named anywhere inside a check document."""
    out: set[str] = set()
    if isinstance(check, dict):
        t = check.get("tool")
        if isinstance(t, str) and t != "*":
            out.add(t)
        for v in check.values():
            out |= _tools_in(v)
    elif isinstance(check, list):
        for v in check:
            out |= _tools_in(v)
    return out


async def _version(s: AsyncSession, ws: str, vid: str) -> m.AgentVersion:
    row = await s.get(m.AgentVersion, vid)
    if row is None or row.workspace_id != ws:
        raise not_found("agent version", vid)
    return row


async def _policy_rules(s: AsyncSession, ws: str, ref: str) -> dict[str, Any]:
    pid, _, ver = ref.partition("@")
    q = select(PolicyVersion).where(PolicyVersion.workspace_id == ws, PolicyVersion.id == pid)
    q = (
        q.where(PolicyVersion.version == int(ver))
        if ver.isdigit()
        else q.order_by(PolicyVersion.version.desc()).limit(1)
    )
    row = (await s.execute(q)).scalars().first()
    if row is None:
        raise not_found("policy", ref)
    return {r["id"]: r for r in row.doc.get("rules", [])}


async def _changed_clauses(s: AsyncSession, ws: str, old: str | None, new: str | None) -> set[str]:
    if old is None or new is None:
        if old is not None or new is not None:
            raise ApiError(422, "validation_error", "policy_from and policy_to go together")
        return set()
    a, b = await _policy_rules(s, ws, old), await _policy_rules(s, ws, new)
    return {rid for rid in a.keys() | b.keys() if a.get(rid) != b.get(rid)}


async def _history(s: AsyncSession, ws: str, old: m.AgentVersion) -> ImpactHistory:
    rows = (
        await s.execute(
            select(m.Scenario)
            .where(
                m.Scenario.workspace_id == ws,
                m.Scenario.status == "approved",
                m.Scenario.quarantined.is_(False),
            )
            .order_by(m.Scenario.id, m.Scenario.version.desc())
        )
    ).scalars()
    latest: dict[str, m.Scenario] = {}
    for r in rows:
        latest.setdefault(r.id, r)
    # tools called in past episodes of the old version
    past: dict[str, set[str]] = {}
    for sid, tool in (
        await s.execute(
            text(
                "SELECT DISTINCT e.scenario_id, ev.doc #>> '{payload,tool}' FROM events ev "
                "JOIN episodes e ON e.id = ev.episode_id JOIN runs r ON r.id = e.run_id "
                "WHERE ev.kind = 'tool_call' AND r.workspace_id = :ws "
                "AND r.agent_version_id = :v"
            ),
            {"ws": ws, "v": old.id},
        )
    ).all():
        if tool:
            past.setdefault(sid, set()).add(tool)
    infos = []
    for sid, row in sorted(latest.items()):
        doc = row.doc
        tools = (
            _tools_in(doc.get("success")) | _tools_in(doc.get("forbidden")) | past.get(sid, set())
        )
        tags = {str(k): str(v) for k, v in (doc.get("tags") or {}).items()}
        risk = tags.get("risk") if tags.get("risk") in RISKS else None
        if risk is None:
            risk = (
                "high"
                if doc.get("attack") or tags.get("severity") in ("high", "critical")
                else "medium"
            )
        world = doc.get("world")
        infos.append(
            ScenarioInfo(
                id=sid,
                tools=frozenset(tools),
                tags=tags,
                world_id=world if isinstance(world, str) else None,
                risk=risk,
                pinned=row.source == "pinned",
            )
        )
    return ImpactHistory(tuple(infos), await _flipped(s, ws, old.agent_id))


async def _flipped(s: AsyncSession, ws: str, agent_id: str) -> frozenset[str]:
    """Scenarios whose majority outcome differed across the agent's last five finished runs."""
    run_ids = list(
        (
            await s.execute(
                select(m.Run.id)
                .join(m.AgentVersion, m.AgentVersion.id == m.Run.agent_version_id)
                .where(
                    m.Run.workspace_id == ws,
                    m.AgentVersion.agent_id == agent_id,
                    m.Run.status == "done",
                    m.Run.purpose == "eval",
                )
                .order_by(m.Run.finished_at.desc())
                .limit(FLIP_RUNS)
            )
        ).scalars()
    )
    if not run_ids:
        return frozenset()
    rows = (
        await s.execute(
            select(
                m.Episode.scenario_id,
                m.Episode.run_id,
                func.count().filter(m.Episode.outcome == "passed"),
                func.count().filter(m.Episode.outcome == "failed"),
            )
            .where(m.Episode.run_id.in_(run_ids), m.Episode.outcome.in_(("passed", "failed")))
            .group_by(m.Episode.scenario_id, m.Episode.run_id)
        )
    ).all()
    seen: dict[str, set[bool]] = {}
    for sid, _rid, ok, bad in rows:
        seen.setdefault(sid, set()).add(ok >= bad)
    return frozenset(sid for sid, v in seen.items() if len(v) > 1)


async def impact_for_versions(s: AsyncSession, ws: str, body: ImpactIn) -> ImpactOut:
    old, new = await _version(s, ws, body.from_version), await _version(s, ws, body.to_version)
    clauses = await _changed_clauses(s, ws, body.policy_from, body.policy_to)
    worlds = (
        {w for w in {old.world_id, new.world_id} if w} if old.world_id != new.world_id else set()
    )
    change = classify_change(
        old.config, new.config, policy_clauses=frozenset(clauses), worlds=frozenset(worlds)
    )
    history = await _history(s, ws, old)
    out = compute_impact(change, history, seed=f"{old.id}:{new.id}")
    return ImpactOut(
        change=ChangeOut(
            tools=sorted(change.tools), policy_clauses=sorted(change.policy_clauses),
            model=change.model, prompt=change.prompt, worlds=sorted(change.worlds),
            unknown=change.unknown,
        ),
        scenario_ids=out.scenario_ids, reasons=out.reasons, full_run=out.full_run,
        total_scenarios=len(history.scenarios),
        suggested_suite=SuggestedSuite(
            name=f"impact {old.label} to {new.label}", scenario_ids=out.scenario_ids
        ),
    )  # fmt: skip
