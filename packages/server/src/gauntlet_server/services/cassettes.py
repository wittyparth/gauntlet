"""Cassette export, archive and import (P3-3, CQ-R11: imports live in `purpose=import` runs)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from gauntlet_core.engine import JournalSnapshot
from gauntlet_core.eval import load_rubrics
from gauntlet_core.ids import new_id
from gauntlet_core.replay import (
    CassetteError,
    CassetteManifest,
    export_cassette,
    import_cassette,
)
from gauntlet_core.schema import AgentVersion, RunManifest, Scenario
from gauntlet_core.sim import load_persona_library
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Agent, Episode, Project, Run, Suite
from ..db.models import AgentVersion as AgentVersionRow
from ..db.models import Persona as PersonaRow
from ..db.models import Rubric as RubricRow
from ..db.models import Scenario as ScenarioRow
from ..db.models import Verdict as VerdictRow
from ..db.models import World as WorldRow
from ..deps import AppState
from ..errors import ApiError, not_found
from ..jobs import load_episode_inputs
from ..stores import PgJournalStore
from .audit import audit
from .runs import platform_version

__all__ = [
    "MAX_CASSETTE_BYTES",
    "ArchiveOut",
    "ImportOut",
    "archive_cassette",
    "episode_cassette",
    "import_cassette_text",
    "load_journal",
]

MAX_CASSETTE_BYTES = 20 * 1024 * 1024
IMPORT_AGENT = "agent_imported"


class ArchiveOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    url: str


class ImportOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    episode_id: str
    scenario_id: str
    scenario_version: int
    agent_version_id: str
    events: int


async def _owned_episode(s: AsyncSession, ws: str, episode_id: str) -> Episode:
    ep = await s.get(Episode, episode_id)
    if ep is None or ep.workspace_id != ws:
        raise not_found("episode", episode_id)
    return ep


async def load_journal(state: AppState, episode_id: str) -> JournalSnapshot:
    return await PgJournalStore(state.sm).load(episode_id)


async def _secret_values(state: AppState, ws: str) -> list[str]:
    names = [n for n, _ in await state.secrets.names(ws)]
    return list((await state.secrets.resolve(ws, names)).values())


async def episode_cassette(state: AppState, s: AsyncSession, ws: str, episode_id: str) -> str:
    ep = await _owned_episode(s, ws, episode_id)
    if ep.status != "done":
        raise ApiError(409, "episode_not_done", "only a finished episode can be exported")
    inputs = await load_episode_inputs(s, episode_id)
    manifest = CassetteManifest(
        episode_id=episode_id,
        run_id=ep.run_id,
        scenario=inputs.scenario,
        world=inputs.world,
        rng_seed=int(ep.rng_seed),
        agent_version=inputs.manifest.agent_version,
        persona=inputs.persona,
        rubrics=inputs.rubrics,
        rubric_order=list(inputs.rubrics),
        platform_version=platform_version(),
    )
    snap = await load_journal(state, episode_id)
    return export_cassette(snap, manifest, secrets=await _secret_values(state, ws))


async def archive_cassette(
    state: AppState, s: AsyncSession, ws: str, episode_id: str, actor: str
) -> ArchiveOut:
    if state.object_store is None:
        raise ApiError(503, "object_store_unavailable", "no object store is configured")
    text_ = await episode_cassette(state, s, ws, episode_id)
    key = f"cassettes/{ws}/{episode_id}.jsonl"
    await state.object_store.put(key, text_.encode(), "application/x-ndjson")
    await audit(s, ws, actor, "cassette.archived", "episode", episode_id, {"key": key})
    return ArchiveOut(key=key, url=await state.object_store.url(key, 3600))


# ------------------------------------------------------------------------------ import


def _doc(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json", exclude_none=True)


async def _upsert_versioned(
    s: AsyncSession, table: Any, ws: str, doc_id: str, doc: dict[str, Any]
) -> int:
    """The version of `doc` under `doc_id`: the latest if identical, else a new one."""
    latest = (
        await s.execute(
            select(table)
            .where(table.workspace_id == ws, table.id == doc_id)
            .order_by(table.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest is not None:
        same = {k: v for k, v in latest.doc.items() if k != "version"} == {
            k: v for k, v in doc.items() if k != "version"
        }
        if same:
            return int(latest.version)
    version = (latest.version + 1) if latest is not None else 1
    kwargs: dict[str, Any] = {}
    if table is ScenarioRow:
        kwargs = {"status": "draft", "source": "pinned"}
    s.add(
        table(
            id=doc_id, version=version, workspace_id=ws, doc={**doc, "version": version}, **kwargs
        )
    )
    await s.flush()
    return version


async def _ensure_missing(
    s: AsyncSession, table: Any, ws: str, doc_id: str, doc: dict[str, Any], library: set[str]
) -> None:
    if doc_id in library:
        return
    have = (
        await s.execute(select(table.id).where(table.workspace_id == ws, table.id == doc_id))
    ).first()
    if have is None:
        s.add(table(id=doc_id, version=1, workspace_id=ws, doc=doc))
        await s.flush()


async def _import_agent(s: AsyncSession, ws: str, given: str | None, av: AgentVersion) -> str:
    if given is not None:
        row = await s.get(AgentVersionRow, given)
        if row is None or row.workspace_id != ws:
            raise not_found("agent version", given)
        return row.id
    if await s.get(Agent, IMPORT_AGENT + "_" + _short(ws)) is None:
        proj = (
            (
                await s.execute(
                    select(Project).where(Project.workspace_id == ws).order_by(Project.created_at)
                )
            )
            .scalars()
            .first()
        )
        if proj is None:
            proj = Project(id=new_id("proj"), workspace_id=ws, name="Imported")
            s.add(proj)
            await s.flush()
        s.add(
            Agent(
                id=IMPORT_AGENT + "_" + _short(ws),
                workspace_id=ws,
                project_id=proj.id,
                name="Imported cassettes",
            )
        )
        await s.flush()
    config = av.model_dump(mode="json", exclude={"id", "agent_id", "label"}, exclude_none=True)
    row = AgentVersionRow(
        id=new_id("agv"),
        workspace_id=ws,
        agent_id=IMPORT_AGENT + "_" + _short(ws),
        label="imported",
        config=config,
    )
    s.add(row)
    await s.flush()
    return row.id


def _short(ws: str) -> str:
    return hashlib.sha256(ws.encode()).hexdigest()[:10]


async def _import_suite(s: AsyncSession, ws: str) -> str:
    sid = "suite_imported_" + _short(ws)
    if await s.get(Suite, sid) is None:
        s.add(Suite(id=sid, workspace_id=ws, name="Imported cassettes", repetitions=1))
        await s.flush()
    return sid


async def import_cassette_text(
    state: AppState,
    s: AsyncSession,
    ws: str,
    body: str,
    agent_version_id: str | None,
    actor: str,
) -> ImportOut:
    """Validate, store scenario / world / personas / rubrics (version bump when different),
    create a completed `purpose=import` run with one finished episode, and write its journal
    directly (no lease)."""
    if len(body.encode()) > MAX_CASSETTE_BYTES:
        raise ApiError(413, "cassette_too_large", "cassettes are limited to 20 MB")
    try:
        snap, man = import_cassette(body)
    except CassetteError as exc:
        raise ApiError(
            422, "invalid_cassette", str(exc), {"line": exc.line} if exc.line else None
        ) from exc
    ended = next((e for e in reversed(snap.events) if e.kind == "episode_ended"), None)
    if ended is None:
        raise ApiError(422, "invalid_cassette", "the cassette has no episode_ended event")
    scn: Scenario = man.scenario
    world_versions: dict[str, int] = {}
    if isinstance(scn.world, str):
        wver = await _upsert_versioned(s, WorldRow, ws, scn.world, _doc(man.world))
        world_versions[scn.world] = wver
    scn_doc = _doc(scn)
    version = await _upsert_versioned(s, ScenarioRow, ws, scn.id, scn_doc)
    await _ensure_missing(
        s, PersonaRow, ws, man.persona.id, _doc(man.persona), set(load_persona_library())
    )
    for rid, rubric in man.rubrics.items():
        await _ensure_missing(s, RubricRow, ws, rid, _doc(rubric), set(load_rubrics()))
    av_id = await _import_agent(s, ws, agent_version_id, man.agent_version)
    suite_id = await _import_suite(s, ws)
    run_id, ep_id = new_id("run"), new_id("ep")
    now = datetime.now(UTC)
    manifest = RunManifest(
        run_id=run_id,
        suite_id=suite_id,
        agent_version=man.agent_version,
        scenario_versions={scn.id: version},
        seed=0,
        repetitions=1,
        model_roles={},
        platform_version=platform_version(),
        budget_usd_micros=0,
        created_at=now,
    )
    s.add(
        Run(
            id=run_id,
            workspace_id=ws,
            suite_id=suite_id,
            agent_version_id=av_id,
            manifest=manifest.model_dump(mode="json"),
            status="done",
            repetitions=1,
            seed=0,
            world_versions=world_versions,
            budget_usd_micros=0,
            purpose="import",
            finished_at=now,
        )
    )
    await s.flush()
    wall = sum(e.wall_ms for e in snap.events if e.kind in ("agent_message", "tool_result"))
    tin = sum(r.cost.input_tokens for r in snap.effects.values() if r.cost and r.status == "done")
    tout = sum(r.cost.output_tokens for r in snap.effects.values() if r.cost and r.status == "done")
    s.add(
        Episode(
            id=ep_id,
            workspace_id=ws,
            run_id=run_id,
            scenario_id=scn.id,
            scenario_version=version,
            rep=0,
            status="done",
            outcome=ended.payload.get("outcome"),
            termination=ended.payload.get("termination"),
            epoch=0,
            rng_seed=man.rng_seed,
            latency_ms=wall,
            tokens_in=tin,
            tokens_out=tout,
            finished_at=now,
        )
    )
    await s.flush()
    await s.commit()  # PgJournalStore writes in its own transaction: the episode row must exist
    await PgJournalStore(state.sm).append(
        ep_id, 0, events=snap.events, effects=list(snap.effects.values())
    )
    for e in snap.events:
        if e.kind == "verdict":
            s.add(
                VerdictRow(
                    id=new_id("vrd"),
                    workspace_id=ws,
                    episode_id=ep_id,
                    evaluator=str(e.payload.get("evaluator", "")),
                    criterion=str(e.payload.get("criterion", "")),
                    result=str(e.payload.get("result", "")),
                    doc=e.payload,
                )
            )
    await audit(
        s, ws, actor, "cassette.imported", "episode", ep_id,
        {"run_id": run_id, "source_episode": man.episode_id, "events": len(snap.events)},
    )  # fmt: skip
    await s.commit()
    return ImportOut(
        run_id=run_id,
        episode_id=ep_id,
        scenario_id=scn.id,
        scenario_version=version,
        agent_version_id=av_id,
        events=len(snap.events),
    )
