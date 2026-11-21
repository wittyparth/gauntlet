"""Run reports and episode detail, computed on demand from the stored journals."""

from __future__ import annotations

from typing import Any

from gauntlet_core.eval import EpisodeRecord, RunReport, aggregate_run, load_rubrics
from gauntlet_core.schema import Event, RunManifest, Scenario, Verdict, WorldSpec
from gauntlet_core.world import build_world, fold_world
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Episode, Run
from ..db.models import Event as EventRow
from ..db.models import Scenario as ScenarioRow
from ..errors import not_found
from ..jobs import load_episode_inputs
from .stability import quarantined_ids

__all__ = ["episode_detail", "episode_row_json", "run_report", "run_report_and_records"]


async def _events(s: AsyncSession, episode_id: str) -> list[Event]:
    rows = (
        await s.execute(
            select(EventRow.doc).where(EventRow.episode_id == episode_id).order_by(EventRow.seq)
        )
    ).scalars()
    return [Event.model_validate(d) for d in rows]


def episode_row_json(e: Episode) -> dict[str, Any]:
    return {
        "id": e.id,
        "run_id": e.run_id,
        "scenario_id": e.scenario_id,
        "scenario_version": e.scenario_version,
        "rep": e.rep,
        "status": e.status,
        "outcome": e.outcome,
        "termination": e.termination,
        "attempt": e.attempt,
        "cost_usd_micros": e.cost_usd_micros,
        "world_fidelity": e.world_fidelity,
        "created_at": e.created_at.isoformat(),
        "finished_at": e.finished_at.isoformat() if e.finished_at else None,
    }


async def run_report(s: AsyncSession, run: Run) -> RunReport:
    return (await run_report_and_records(s, run))[0]


async def run_report_and_records(
    s: AsyncSession, run: Run
) -> tuple[RunReport, list[EpisodeRecord]]:
    manifest = RunManifest.model_validate(run.manifest)
    eps = (
        (
            await s.execute(
                select(Episode)
                .where(Episode.run_id == run.id, Episode.status == "done")
                .order_by(Episode.scenario_id, Episode.rep)
            )
        )
        .scalars()
        .all()
    )
    scenario_rows = (
        await s.execute(
            select(ScenarioRow).where(
                ScenarioRow.workspace_id == run.workspace_id,
                ScenarioRow.id.in_(list(manifest.scenario_versions)),
            )
        )
    ).scalars()
    scenarios = {
        r.id: Scenario.model_validate(r.doc)
        for r in scenario_rows
        if manifest.scenario_versions.get(r.id) == r.version
    }
    records: list[EpisodeRecord] = []
    verdicts: dict[str, list[Verdict]] = {}
    for e in eps:
        events = await _events(s, e.id)
        reasons = [
            ev.payload["check_id"]
            for ev in events
            if ev.kind == "check_result"
            and ev.payload["holds"] != (ev.payload["check_id"] == "success")
        ]
        verdicts[e.id] = [
            Verdict.model_validate(ev.payload) for ev in events if ev.kind == "verdict"
        ]
        records.append(
            EpisodeRecord(
                e.id,
                e.scenario_id,
                e.rep,
                e.outcome or "platform_error",
                e.termination,
                int(e.cost_usd_micros),
                int(e.latency_ms)
                if e.latency_ms is not None
                else sum(
                    ev.wall_ms for ev in events if ev.kind in ("agent_message", "tool_result")
                ),
                e.world_fidelity,
                tuple(reasons),
            )
        )
    cfg = manifest.agent_version.target
    report = aggregate_run(
        run.id,
        records,
        verdicts,
        scenarios,
        seed=run.seed,
        judge_model=manifest.model_roles.get("judge_small"),
        target_model=getattr(cfg, "model", None),
        target_kind=cfg.kind,
        wired=bool(getattr(cfg, "wired", False)),
        rubrics=load_rubrics(),
        quarantined=await quarantined_ids(s, run.workspace_id),
        adaptive=run.adaptive,
        repetitions=run.repetitions,
    )
    return report, records


async def episode_detail(
    s: AsyncSession, ws: str, episode_id: str, *, events_mode: str = "all"
) -> dict[str, Any]:
    ep = await s.get(Episode, episode_id)
    if ep is None or ep.workspace_id != ws:
        raise not_found("episode", episode_id)
    inputs = await load_episode_inputs(s, episode_id)
    events = await _events(s, episode_id)
    built = build_world(inputs.world, inputs.scenario.world_overrides, int(ep.rng_seed))
    _, diff = fold_world(built.initial, events)
    scn = inputs.scenario
    shown = events if events_mode == "all" else [e for e in events if e.kind != "tool_result"]
    return {
        **episode_row_json(ep),
        "scenario": {
            "id": scn.id,
            "title": scn.title,
            "goal": scn.goal,
            "max_turns": scn.max_turns,
            "tags": scn.tags,
        },
        "partial": ep.status != "done",
        "events": shown,
        "verdicts": [e.payload for e in events if e.kind == "verdict"],
        "diff": diff,
        "tools": {t.name: t.risk for t in _tools(inputs.world)},
    }


def _tools(world: WorldSpec) -> list[Any]:
    return list(world.tools)


async def episode_count(s: AsyncSession, run_id: str) -> int:
    return int(
        (
            await s.execute(text("SELECT count(*) FROM episodes WHERE run_id = :r"), {"r": run_id})
        ).scalar()
        or 0
    )
