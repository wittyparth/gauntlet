"""Episode replay (P3-3): `strict` runs in-process and answers at once; `agent_live` creates a
`purpose=replay` run whose single episode starts from a copy of the recording."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from gauntlet_core.engine import fork_for_agent_live
from gauntlet_core.ids import new_id
from gauntlet_core.replay import Divergence, replay_strict
from gauntlet_core.schema import RunManifest
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import AgentVersion as AgentVersionRow
from ..db.models import Episode, Run
from ..deps import AppState
from ..errors import ApiError, not_found
from ..jobs import load_episode_inputs
from ..stores import PgJournalStore
from .audit import audit
from .cassettes import episode_cassette
from .runs import agent_version_of

__all__ = ["ReplayIn", "ReplayOut", "replay_episode"]

DEFAULT_BUDGET = 1_000_000


class ReplayIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["strict", "agent_live"]
    agent_version_id: str | None = None
    budget_usd_micros: int | None = None


class ReplayOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["strict", "agent_live"]
    identical: bool | None = None  # strict
    events: int | None = None  # strict
    divergence: Divergence | None = None  # strict
    run_id: str | None = None  # agent_live: the replay run
    episode_id: str | None = None  # agent_live: its episode


async def replay_episode(
    state: AppState, s: AsyncSession, ws: str, episode_id: str, body: ReplayIn, actor: str
) -> ReplayOut:
    ep = await s.get(Episode, episode_id)
    if ep is None or ep.workspace_id != ws:
        raise not_found("episode", episode_id)
    if body.mode == "strict":
        rep = await replay_strict(await episode_cassette(state, s, ws, episode_id))
        return ReplayOut(
            mode="strict", identical=rep.identical, events=rep.events, divergence=rep.divergence
        )
    return await _agent_live(state, s, ws, ep, body, actor)


async def _agent_live(
    state: AppState, s: AsyncSession, ws: str, ep: Episode, body: ReplayIn, actor: str
) -> ReplayOut:
    if ep.status != "done":
        raise ApiError(409, "episode_not_done", "only a finished episode can be replayed")
    inputs = await load_episode_inputs(s, ep.id)
    src_run = inputs.run
    version = inputs.manifest.agent_version
    if body.agent_version_id is not None:
        av = await s.get(AgentVersionRow, body.agent_version_id)
        if av is None or av.workspace_id != ws:
            raise not_found("agent version", body.agent_version_id)
        version = agent_version_of(av)
    budget = min(body.budget_usd_micros or DEFAULT_BUDGET, state.settings.max_run_budget_usd_micros)
    if budget <= 0:
        raise ApiError(422, "budget_too_low", "budget must be positive")
    run_id, new_ep = new_id("run"), new_id("ep")
    manifest = RunManifest(
        **{
            **inputs.manifest.model_dump(),
            "run_id": run_id,
            "agent_version": version,
            "scenario_versions": {ep.scenario_id: ep.scenario_version or 1},
            "repetitions": 1,
            "budget_usd_micros": budget,
            "created_at": datetime.now(UTC),
        }
    )
    s.add(
        Run(
            id=run_id,
            workspace_id=ws,
            suite_id=src_run.suite_id,
            agent_version_id=body.agent_version_id or src_run.agent_version_id,
            manifest=manifest.model_dump(mode="json"),
            role_settings=src_run.role_settings,
            status="queued",
            repetitions=1,
            seed=src_run.seed,
            world_versions=src_run.world_versions,
            budget_usd_micros=budget,
            purpose="replay",
        )
    )
    await s.flush()
    s.add(
        Episode(
            id=new_ep,
            workspace_id=ws,
            run_id=run_id,
            scenario_id=ep.scenario_id,
            scenario_version=ep.scenario_version,
            rep=0,
            rng_seed=ep.rng_seed,
            # held back until the recording is copied in (the copy has its own transaction)
            not_before=_far(),
        )
    )
    await audit(
        s, ws, actor, "episode.replay_started", "episode", ep.id,
        {"run_id": run_id, "episode_id": new_ep, "mode": "agent_live"},
    )  # fmt: skip
    await s.commit()
    await fork_for_agent_live(PgJournalStore(state.sm), ep.id, new_ep)
    await s.execute(text("UPDATE episodes SET not_before = now() WHERE id = :e"), {"e": new_ep})
    await s.commit()
    return ReplayOut(mode="agent_live", run_id=run_id, episode_id=new_ep)


def _far() -> datetime:
    return datetime(2100, 1, 1, tzinfo=UTC)
