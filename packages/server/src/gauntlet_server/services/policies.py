"""Policy compiler service (P4-1): compile job, review flow, immutable versions, coverage.

Versions: `compile` creates version 1 as a `draft` with its proposals. Editing proposals of a
published version creates a draft `version + 1`. Publishing promotes the latest draft in place,
or, when the latest version is already published (a mode change), writes a new published
version. A published row is never updated."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from gauntlet_core.ids import new_id
from gauntlet_core.policy import validate_policy
from gauntlet_core.policy.compile import (
    CompiledPolicy,
    CoverageReport,
    accepted_proposals,
    check_rule,
    compile_policy,
    coverage_report,
)
from gauntlet_core.schema import Policy, Trajectory, WorldSpec
from gauntlet_core.world import build_trajectory, build_world
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import AgentVersion, Episode, Run, World
from ..db.policy_models import PolicyProposalRow, PolicyVersion
from ..deps import AppState
from ..errors import ApiError, not_found
from ..jobs import load_episode_inputs
from ..stores.jobs import PgJobQueue
from .audit import audit
from .jobs import JobContext, handler
from .reports import _events

__all__ = [
    "CompileIn",
    "CompileStarted",
    "PatchIn",
    "PolicyOut",
    "PublishIn",
    "coverage_for",
    "enqueue_compile",
    "get_policy",
    "get_proposals",
    "list_policies",
    "patch_proposal",
    "publish_policy",
]

JOB_KIND = "compile_policy"


class CompileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    agent_id: str | None = None
    text: str | None = None
    tools_from_world_id: str | None = None
    seed: int = 0


class CompileStarted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    policy_id: str


class PatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["proposed", "accepted", "rejected", "edited"]
    rule: dict[str, Any] | None = None


class PublishIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["shadow", "enforce"] = "shadow"
    fail: Literal["open", "closed"] = "open"


class PolicyOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    version: int
    name: str
    status: Literal["draft", "published"]
    agent_id: str | None
    policy: Policy
    source_text: str
    created_at: datetime


def _out(row: PolicyVersion) -> PolicyOut:
    return PolicyOut(
        id=row.id,
        version=row.version,
        name=row.name,
        status=row.status,  # type: ignore[arg-type]
        agent_id=row.agent_id,
        policy=Policy.model_validate(row.doc),
        source_text=row.source_text,
        created_at=row.created_at,
    )


# -- compile ------------------------------------------------------------------------------


async def _world_tools(s: AsyncSession, ws: str, world_id: str) -> WorldSpec:
    row = (
        await s.execute(
            select(World)
            .where(World.workspace_id == ws, World.id == world_id)
            .order_by(World.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise not_found("world", world_id)
    return WorldSpec.model_validate(row.doc)


async def enqueue_compile(
    state: AppState, s: AsyncSession, ws: str, body: CompileIn, actor: str
) -> CompileStarted:
    if (body.agent_id is None) == (body.text is None):
        raise ApiError(422, "validation_error", "give exactly one of agent_id or text")
    text = body.text
    world_id = body.tools_from_world_id
    if body.agent_id is not None:
        av = (
            await s.execute(
                select(AgentVersion)
                .where(AgentVersion.workspace_id == ws, AgentVersion.agent_id == body.agent_id)
                .order_by(AgentVersion.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if av is None:
            raise not_found("agent", body.agent_id)
        text = str((av.config.get("profile") or {}).get("policies_text") or "")
        world_id = world_id or av.world_id
        if not text.strip():
            raise ApiError(422, "validation_error", "the agent has no policy text to compile")
    if world_id is not None:
        await _world_tools(s, ws, world_id)  # 404 early
    if not (text or "").strip():
        raise ApiError(422, "validation_error", "policy text is empty")
    policy_id = new_id("pol")
    job_id = await PgJobQueue(state.sm).enqueue(
        ws,
        JOB_KIND,
        {
            "policy_id": policy_id,
            "name": body.name,
            "text": text,
            "agent_id": body.agent_id,
            "world_id": world_id,
            "seed": body.seed,
        },
        session=s,
    )
    await audit(s, ws, actor, "policy.compile_requested", "policy", policy_id, {"job_id": job_id})
    await s.commit()
    return CompileStarted(job_id=job_id, policy_id=policy_id)


@handler(JOB_KIND)
async def compile_job(ctx: JobContext) -> dict[str, Any]:
    p = ctx.payload
    policy_id, ws = str(p["policy_id"]), ctx.workspace_id
    async with ctx.state.sm() as s:
        tools = (await _world_tools(s, ws, p["world_id"])).tools if p.get("world_id") else []
    compiled = await compile_policy(
        str(p["text"]),
        tools=tools,
        gateway=ctx.state.gateway,
        policy_id=policy_id,
        seed=int(p.get("seed", 0)),
    )
    async with ctx.state.sm() as s, s.begin():
        if await s.get(PolicyVersion, (policy_id, 1)) is None:  # at-least-once: write once
            s.add(
                PolicyVersion(
                    id=policy_id,
                    version=1,
                    workspace_id=ws,
                    name=str(p["name"]),
                    agent_id=p.get("agent_id"),
                    doc=Policy(id=policy_id, version=1, rules=[]).model_dump(mode="json"),
                    status="draft",
                    source_text=str(p["text"]),
                )
            )
            s.add(
                PolicyProposalRow(
                    id=new_id("ppr"),
                    workspace_id=ws,
                    policy_id=policy_id,
                    version=1,
                    doc=compiled.model_dump(mode="json"),
                )
            )
            await audit(
                s,
                ws,
                "system",
                "policy.compiled",
                "policy",
                policy_id,
                {"proposals": len(compiled.proposals), "cost_usd_micros": compiled.cost.usd_micros},
            )
    return {
        "policy_id": policy_id,
        "version": 1,
        "proposals": len(compiled.proposals),
        "cost_usd_micros": compiled.cost.usd_micros,
    }


# -- reads --------------------------------------------------------------------------------


async def _row(s: AsyncSession, ws: str, policy_id: str, version: int | None) -> PolicyVersion:
    q = select(PolicyVersion).where(PolicyVersion.workspace_id == ws, PolicyVersion.id == policy_id)
    q = q.where(PolicyVersion.version == version) if version else q
    row = (await s.execute(q.order_by(PolicyVersion.version.desc()).limit(1))).scalar_one_or_none()
    if row is None:
        raise not_found("policy", policy_id)
    return row


async def _proposals_row(
    s: AsyncSession, ws: str, policy_id: str, version: int
) -> PolicyProposalRow:
    row = (
        await s.execute(
            select(PolicyProposalRow).where(
                PolicyProposalRow.workspace_id == ws,
                PolicyProposalRow.policy_id == policy_id,
                PolicyProposalRow.version == version,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise not_found("proposals of policy", policy_id)
    return row


async def list_policies(s: AsyncSession, ws: str) -> list[PolicyOut]:
    """The latest version of each policy, newest first."""
    rows = (
        (
            await s.execute(
                select(PolicyVersion)
                .where(PolicyVersion.workspace_id == ws)
                .order_by(PolicyVersion.id, PolicyVersion.version.desc())
            )
        )
        .scalars()
        .all()
    )
    latest = {r.id: r for r in reversed(rows)}  # rows run newest version first per id
    return [_out(r) for r in sorted(latest.values(), key=lambda r: r.created_at, reverse=True)]


async def get_policy(s: AsyncSession, ws: str, policy_id: str, version: int | None) -> PolicyOut:
    return _out(await _row(s, ws, policy_id, version))


async def get_proposals(
    s: AsyncSession, ws: str, policy_id: str, version: int | None
) -> CompiledPolicy:
    row = await _row(s, ws, policy_id, version)
    return CompiledPolicy.model_validate((await _proposals_row(s, ws, policy_id, row.version)).doc)


# -- review -------------------------------------------------------------------------------


async def _editable(
    s: AsyncSession, ws: str, policy_id: str
) -> tuple[PolicyVersion, PolicyProposalRow]:
    """The latest draft; a draft `version + 1` is created when the latest is published."""
    latest = await _row(s, ws, policy_id, None)
    props = await _proposals_row(s, ws, policy_id, latest.version)
    if latest.status == "draft":
        return latest, props
    nv = latest.version + 1
    draft = PolicyVersion(
        id=policy_id,
        version=nv,
        workspace_id=ws,
        name=latest.name,
        agent_id=latest.agent_id,
        doc={**latest.doc, "version": nv},
        status="draft",
        source_text=latest.source_text,
    )
    copied = PolicyProposalRow(
        id=new_id("ppr"), workspace_id=ws, policy_id=policy_id, version=nv, doc=dict(props.doc)
    )
    s.add_all([draft, copied])
    await s.flush()
    return draft, copied


async def patch_proposal(
    s: AsyncSession, ws: str, policy_id: str, clause_id: str, body: PatchIn, actor: str
) -> CompiledPolicy:
    draft, row = await _editable(s, ws, policy_id)
    compiled = CompiledPolicy.model_validate(row.doc)
    prop = next((p for p in compiled.proposals if p.clause_id == clause_id), None)
    if prop is None:
        raise not_found("clause", clause_id)
    status: str = body.status
    if body.rule is not None:
        if prop.klass == "model":
            raise ApiError(
                422, "validation_error", "a model-class clause takes a rubric, not a rule"
            )
        if status == "rejected":
            raise ApiError(422, "validation_error", "a rejected proposal cannot carry an edit")
        res = check_rule(body.rule, [])
        if res.rule is None or res.fatal:
            raise ApiError(422, "validation_error", "invalid rule", res.problems)
        prop = prop.model_copy(update={"rule": res.rule})
        status = "edited"
    prop = prop.model_copy(update={"status": status})
    compiled = compiled.model_copy(
        update={"proposals": [prop if p.clause_id == clause_id else p for p in compiled.proposals]}
    )
    row.doc = compiled.model_dump(mode="json")
    await audit(
        s,
        ws,
        actor,
        "policy.proposal_updated",
        "policy",
        policy_id,
        {"version": draft.version, "clause_id": clause_id, "status": status},
    )
    await s.commit()
    return compiled


async def publish_policy(
    s: AsyncSession, ws: str, policy_id: str, body: PublishIn, actor: str
) -> PolicyOut:
    latest = await _row(s, ws, policy_id, None)
    props_row = await _proposals_row(s, ws, policy_id, latest.version)
    compiled = CompiledPolicy.model_validate(props_row.doc)
    accepted = accepted_proposals(compiled)
    rules = [p.rule for p in accepted if p.rule is not None]
    if not accepted:
        raise ApiError(422, "no_accepted_proposals", "accept at least one proposal first")
    if not rules:
        raise ApiError(422, "no_accepted_proposals", "no accepted proposal carries a rule")
    version = latest.version if latest.status == "draft" else latest.version + 1
    policy = Policy(id=policy_id, version=version, rules=rules, mode=body.mode, fail=body.fail)
    problems = validate_policy(policy)
    if problems:
        raise ApiError(
            422, "validation_error", "the accepted rules do not form a valid policy", problems
        )
    doc = policy.model_dump(mode="json")
    if latest.status == "draft":
        latest.doc, latest.status = doc, "published"
        out_row = latest
    else:
        out_row = PolicyVersion(
            id=policy_id,
            version=version,
            workspace_id=ws,
            name=latest.name,
            agent_id=latest.agent_id,
            doc=doc,
            status="published",
            source_text=latest.source_text,
        )
        s.add(out_row)
        s.add(
            PolicyProposalRow(
                id=new_id("ppr"),
                workspace_id=ws,
                policy_id=policy_id,
                version=version,
                doc=dict(props_row.doc),
            )
        )
    await audit(
        s,
        ws,
        actor,
        "policy.published",
        "policy",
        policy_id,
        {
            "version": version,
            "rule_ids": [r.id for r in rules],
            "mode": body.mode,
            "fail": body.fail,
        },
    )
    await s.commit()
    await s.refresh(out_row)
    return _out(out_row)


# -- coverage -----------------------------------------------------------------------------


async def _run_trajectories(s: AsyncSession, ws: str, run_id: str) -> list[Trajectory]:
    run = await s.get(Run, run_id)
    if run is None or run.workspace_id != ws:
        raise not_found("run", run_id)
    eps = (
        (
            await s.execute(
                select(Episode)
                .where(Episode.run_id == run_id, Episode.status == "done")
                .order_by(Episode.id)
            )
        )
        .scalars()
        .all()
    )
    out: list[Trajectory] = []
    for ep in eps:
        inputs = await load_episode_inputs(s, ep.id)
        events = await _events(s, ep.id)
        built = build_world(inputs.world, inputs.scenario.world_overrides, int(ep.rng_seed))
        out.append(build_trajectory(ep.id, inputs.scenario, events, built))
    return out


async def coverage_for(
    s: AsyncSession, ws: str, policy_id: str, version: int | None, run_id: str | None
) -> CoverageReport:
    compiled = await get_proposals(s, ws, policy_id, version)
    trajs = await _run_trajectories(s, ws, run_id) if run_id else None
    return coverage_report(compiled, trajs)
