"""Blast radius and permission diff of agent versions (P4-5)."""

from __future__ import annotations

from collections.abc import Sequence

from gauntlet_core.policy.blast import (
    BlastRadius,
    PermissionDiff,
    blast_radius,
    observe,
    permission_diff,
)
from gauntlet_core.schema import Policy, ToolSpec, WorldSpec
from gauntlet_core.world import build_trajectory, build_world
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import models as m
from ..db.policy_models import PolicyVersion
from ..errors import ApiError, not_found
from ..jobs import load_episode_inputs
from .reports import _events

__all__ = ["blast_for_version", "diff_versions"]

OBSERVED_EPISODES = 200


async def _version(s: AsyncSession, ws: str, agent_id: str, version_id: str) -> m.AgentVersion:
    av = await s.get(m.AgentVersion, version_id)
    if av is None or av.workspace_id != ws or av.agent_id != agent_id:
        raise not_found("agent version", version_id)
    return av


async def _tools(s: AsyncSession, ws: str, av: m.AgentVersion) -> list[ToolSpec]:
    """The tools of the version's world, narrowed to the hosted target's own subset."""
    if not av.world_id:
        raise ApiError(422, "no_world", "this agent version has no world to read tools from")
    row = (
        await s.execute(
            select(m.World)
            .where(m.World.workspace_id == ws, m.World.id == av.world_id)
            .order_by(m.World.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise not_found("world", av.world_id)
    tools = WorldSpec.model_validate(row.doc).tools
    subset = (av.config.get("target") or {}).get("tools")
    return [t for t in tools if t.name in subset] if subset else list(tools)


async def _policy(s: AsyncSession, ws: str, policy_id: str | None) -> Policy | None:
    if policy_id is None:
        return None
    row = (
        await s.execute(
            select(PolicyVersion)
            .where(PolicyVersion.workspace_id == ws, PolicyVersion.id == policy_id)
            .order_by(PolicyVersion.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise not_found("policy", policy_id)
    return Policy.model_validate(row.doc)


async def blast_for_version(
    s: AsyncSession, ws: str, agent_id: str, version_id: str, policy_id: str | None
) -> BlastRadius:
    av = await _version(s, ws, agent_id, version_id)
    tools = await _tools(s, ws, av)
    eps = (
        (
            await s.execute(
                select(m.Episode)
                .join(m.Run, m.Run.id == m.Episode.run_id)
                .where(
                    m.Run.workspace_id == ws,
                    m.Run.agent_version_id == av.id,
                    m.Episode.status == "done",
                )
                .order_by(m.Episode.created_at.desc())
                .limit(OBSERVED_EPISODES)
            )
        )
        .scalars()
        .all()
    )
    trajs = []
    for ep in eps:
        inputs = await load_episode_inputs(s, ep.id)
        built = build_world(inputs.world, inputs.scenario.world_overrides, int(ep.rng_seed))
        trajs.append(build_trajectory(ep.id, inputs.scenario, await _events(s, ep.id), built))
    return blast_radius(tools, observe(trajs), await _policy(s, ws, policy_id))


async def diff_versions(
    s: AsyncSession, ws: str, agent_id: str, old_id: str, new_id: str, policy_id: str | None
) -> PermissionDiff:
    old: Sequence[ToolSpec] = await _tools(s, ws, await _version(s, ws, agent_id, old_id))
    new: Sequence[ToolSpec] = await _tools(s, ws, await _version(s, ws, agent_id, new_id))
    return permission_diff(old, new, await _policy(s, ws, policy_id))
