"""Baselines, run comparison and trajectory diff (P3-1)."""

from __future__ import annotations

from gauntlet_core.eval import (
    CompareReport,
    RunData,
    TrajectoryDiff,
    compare_runs,
    diff_trajectories,
)
from gauntlet_core.schema import Event, RunManifest, Trajectory
from gauntlet_core.world import build_trajectory, build_world
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Episode, Run
from ..db.sec_models import Finding as FindingRow
from ..db.sec_models import FindingEpisode
from ..errors import ApiError, not_found
from ..jobs import load_episode_inputs
from .reports import _events, run_report_and_records
from .stability import quarantined_ids

__all__ = [
    "FindingsDeltaOut",
    "check_baseline",
    "compare_for_run",
    "episode_diff",
    "findings_delta",
    "set_baseline",
]


async def _owned_run(s: AsyncSession, ws: str, run_id: str) -> Run:
    run = await s.get(Run, run_id)
    if run is None or run.workspace_id != ws:
        raise not_found("run", run_id)
    return run


def check_baseline(run: Run | None, baseline: Run) -> None:
    """The rules of `PUT /v1/runs/{id}/baseline`; `run` is None while the run is being created."""
    if baseline.status != "done" or (run is not None and run.status != "done"):
        raise ApiError(409, "run_not_completed", "both runs must be completed")
    if run is not None and run.id == baseline.id:
        raise ApiError(422, "invalid_baseline", "a run cannot be its own baseline")
    if run is not None and run.suite_id != baseline.suite_id:
        raise ApiError(422, "suite_mismatch", "baseline and run must use the same suite")


async def set_baseline(s: AsyncSession, ws: str, run_id: str, baseline_id: str | None) -> Run:
    run = await _owned_run(s, ws, run_id)
    if baseline_id is None:
        run.baseline_of = None
        return run
    baseline = await _owned_run(s, ws, baseline_id)
    check_baseline(run, baseline)
    run.baseline_of = baseline.id
    return run


async def run_data(s: AsyncSession, run: Run) -> RunData:
    report, records = await run_report_and_records(s, run)
    manifest = RunManifest.model_validate(run.manifest)
    cfg = manifest.agent_version.target
    return RunData(
        run_id=run.id,
        suite_id=run.suite_id,
        scenario_versions=dict(manifest.scenario_versions),
        records=records,
        report=report,
        agent_label=manifest.agent_version.label,
        model=getattr(cfg, "model", None),
        quarantined=frozenset(await quarantined_ids(s, run.workspace_id)),
        rubric_versions=dict(manifest.rubric_versions),
        repetitions=manifest.repetitions,
        judge_model=manifest.model_roles.get("judge_small"),
        agent_id=manifest.agent_version.agent_id,
    )


async def compare_for_run(
    s: AsyncSession, ws: str, run_id: str, baseline_id: str | None
) -> CompareReport:
    run = await _owned_run(s, ws, run_id)
    baseline_id = baseline_id or run.baseline_of
    if baseline_id is None:
        raise ApiError(404, "not_found", f"run {run_id!r} has no baseline")
    baseline = await _owned_run(s, ws, baseline_id)
    if run.status != "done" or baseline.status != "done":
        raise ApiError(409, "run_not_completed", "both runs must be completed")
    return compare_runs(await run_data(s, baseline), await run_data(s, run))


async def _trajectory(s: AsyncSession, ws: str, episode_id: str) -> Trajectory:
    ep = await s.get(Episode, episode_id)
    if ep is None or ep.workspace_id != ws:
        raise not_found("episode", episode_id)
    inputs = await load_episode_inputs(s, episode_id)
    events: list[Event] = await _events(s, episode_id)
    built = build_world(inputs.world, inputs.scenario.world_overrides, int(ep.rng_seed))
    return build_trajectory(episode_id, inputs.scenario, events, built)


async def episode_diff(s: AsyncSession, ws: str, episode_id: str, against: str) -> TrajectoryDiff:
    a = await _trajectory(s, ws, against)
    b = await _trajectory(s, ws, episode_id)
    return diff_trajectories(a, b)


class NewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    severity: str
    category: str


class FindingsDeltaOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline_id: str
    new_by_severity: dict[str, int]
    new: list[NewFinding]


async def findings_delta(
    s: AsyncSession, ws: str, run_id: str, baseline_id: str | None
) -> FindingsDeltaOut:
    """Findings this run's episodes belong to whose (category, attack) the baseline's agent
    version has never produced. Finding dedup keys include the agent version, so identical
    attacks against two versions are told apart by what they are, not by key."""
    run = await _owned_run(s, ws, run_id)
    baseline_id = baseline_id or run.baseline_of
    if baseline_id is None:
        raise ApiError(404, "not_found", f"run {run_id!r} has no baseline")
    base = await _owned_run(s, ws, baseline_id)
    rows = (
        await s.execute(
            select(FindingRow)
            .join(FindingEpisode, FindingEpisode.finding_id == FindingRow.id)
            .join(Episode, Episode.id == FindingEpisode.episode_id)
            .where(Episode.run_id == run.id, FindingRow.agent_version_id == run.agent_version_id)
            .distinct()
            .order_by(FindingRow.id)
        )
    ).scalars()
    known = {
        (f.category, f.attack_id)
        for f in (
            await s.execute(
                select(FindingRow).where(FindingRow.agent_version_id == base.agent_version_id)
            )
        ).scalars()
    }
    new = [f for f in rows if (f.category, f.attack_id) not in known]
    counts: dict[str, int] = {}
    for f in new:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    return FindingsDeltaOut(
        baseline_id=base.id,
        new_by_severity=counts,
        new=[
            NewFinding(id=f.id, title=f.title, severity=f.severity, category=f.category)
            for f in new
        ],
    )
