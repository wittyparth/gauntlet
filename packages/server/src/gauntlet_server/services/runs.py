"""Runs: creation (with dry run), the response shape, state changes, and completion."""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from gauntlet_core.estimate import estimate_run_cost
from gauntlet_core.eval import load_rubrics
from gauntlet_core.eval.stability import initial_repetitions
from gauntlet_core.ids import new_id
from gauntlet_core.runner import derive_episode_seed
from gauntlet_core.schema import AgentVersion, RunManifest, Scenario, WorldSpec
from gauntlet_core.sim import load_persona_library
from gauntlet_core.validate import validate_scenario
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import AgentVersion as AgentVersionRow
from ..db.models import Episode, Run, Suite, SuiteScenario
from ..db.models import Persona as PersonaRow
from ..db.models import Rubric as RubricRow
from ..db.models import Scenario as ScenarioRow
from ..db.models import World as WorldRow
from ..deps import AppState
from ..errors import ApiError, not_found
from .audit import audit
from .compare import check_baseline
from .model_settings import effective_config, load_choices, resolved_roles
from .ownership import target_host
from .scope import enforce_attack_run, is_attack_run

__all__ = [
    "RunCreate",
    "agent_version_of",
    "create_run",
    "maybe_complete_run",
    "run_counts",
    "run_json",
    "run_update_payload",
    "set_run_status",
]


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    suite_id: str
    agent_version_id: str
    repetitions: int | None = None
    budget_usd_micros: int
    seed: int | None = None
    include_drafts: bool = False
    baseline_run_id: str | None = None
    adaptive: bool = False


def platform_version() -> str:
    try:
        return version("gauntlet-server")
    except PackageNotFoundError:
        return "0.0.0"


def agent_version_of(av: AgentVersionRow) -> AgentVersion:
    return AgentVersion.model_validate(
        {**av.config, "id": av.id, "agent_id": av.agent_id, "label": av.label}
    )


async def run_counts(session: AsyncSession, run_id: str) -> dict[str, Any]:
    rows = await session.execute(
        select(Episode.status, Episode.outcome, func.count())
        .where(Episode.run_id == run_id)
        .group_by(Episode.status, Episode.outcome)
    )
    counts: dict[str, Any] = {"total": 0, "queued": 0, "leased": 0, "done": 0, "cancelled": 0}
    by_outcome: dict[str, int] = {}
    for status, outcome, n in rows:
        counts["total"] += n
        counts[status] += n
        if outcome:
            by_outcome[outcome] = by_outcome.get(outcome, 0) + n
    counts["by_outcome"] = by_outcome
    return counts


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


async def run_json(
    session: AsyncSession, run: Run, *, estimate: dict[str, int] | None = None
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": run.id,
        "suite_id": run.suite_id,
        "agent_version_id": run.agent_version_id,
        "status": run.status,
        "manifest": run.manifest,
        "repetitions": run.repetitions,
        "seed": run.seed,
        "budget_usd_micros": run.budget_usd_micros,
        "reserved_usd_micros": run.reserved_usd_micros,
        "spent_usd_micros": run.spent_usd_micros,
        "baseline_of": run.baseline_of,
        "purpose": run.purpose,
        "finding_id": run.finding_id,
        "adaptive": run.adaptive,
        "counts": await run_counts(session, run.id),
        "created_at": _iso(run.created_at),
        "finished_at": _iso(run.finished_at),
    }
    if estimate is not None:
        out["estimate_usd_micros"] = estimate
    return out


async def run_update_payload(session: AsyncSession, run_id: str) -> dict[str, Any]:
    run = await session.get(Run, run_id, populate_existing=True)
    assert run is not None
    return {
        "run_id": run.id,
        "status": run.status,
        "counts": await run_counts(session, run.id),
        "spent_usd_micros": run.spent_usd_micros,
        "reserved_usd_micros": run.reserved_usd_micros,
    }


async def _latest(session: AsyncSession, model: Any, ws: str, ids: list[str]) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(model)
            .where(model.workspace_id == ws, model.id.in_(ids))
            .order_by(model.id, model.version.desc())
        )
    ).scalars()
    latest: dict[str, Any] = {}
    for r in rows:
        latest.setdefault(r.id, r)
    return latest


async def enforce_daily_budget(
    session: AsyncSession, state: AppState, workspace_id: str, budget: int
) -> None:
    """GAUNTLET_DAILY_BUDGET_USD: refuse a run when the budgets of the runs created in the last
    24 hours plus this one would exceed the cap (committed budget: a safe bound)."""
    cap = state.settings.daily_budget_usd_micros
    if cap <= 0:
        return
    since = datetime.now(UTC) - timedelta(hours=24)
    committed = (
        await session.execute(
            select(func.coalesce(func.sum(Run.budget_usd_micros), 0)).where(
                Run.workspace_id == workspace_id,
                Run.created_at >= since,
                ~Run.id.like("run\\_demo%", escape="\\"),  # scripted demo seed: no spend
            )
        )
    ).scalar_one()
    if committed + budget > cap:
        raise ApiError(
            429,
            "daily_budget_exceeded",
            "the daily spend cap would be exceeded; raise GAUNTLET_DAILY_BUDGET_USD or wait",
            {"cap_usd_micros": cap, "committed_usd_micros": int(committed)},
        )


async def create_run(
    session: AsyncSession,
    state: AppState,
    workspace_id: str,
    body: RunCreate,
    *,
    dry_run: bool = False,
    run_id: str | None = None,
    episode_ids: list[str] | None = None,
    purpose: str = "eval",
    finding_id: str | None = None,
    actor: str = "system",
    enforce_daily: bool = True,
) -> tuple[dict[str, Any], int]:
    """Returns (response, http status). Creates nothing when `dry_run`."""
    suite = await session.get(Suite, body.suite_id)
    if suite is None or suite.workspace_id != workspace_id:
        raise not_found("suite", body.suite_id)
    av = await session.get(AgentVersionRow, body.agent_version_id)
    if av is None or av.workspace_id != workspace_id:
        raise not_found("agent version", body.agent_version_id)
    if body.budget_usd_micros <= 0:
        raise ApiError(422, "budget_too_low", "budget must be positive")
    budget = min(body.budget_usd_micros, state.settings.max_run_budget_usd_micros)
    scn_ids = list(
        (
            await session.execute(
                select(SuiteScenario.scenario_id)
                .where(SuiteScenario.suite_id == suite.id)
                .order_by(SuiteScenario.position)
            )
        ).scalars()
    )
    latest = await _latest(session, ScenarioRow, workspace_id, scn_ids)
    errors: list[dict[str, str]] = []
    scenarios: list[Scenario] = []
    for sid in scn_ids:
        row = latest.get(sid)
        if row is None:
            errors.append({"scenario_id": sid, "code": "not_found", "message": "scenario missing"})
        elif row.status != "approved" and not body.include_drafts:
            errors.append({"scenario_id": sid, "code": "not_approved", "message": "draft scenario"})
        else:
            scenarios.append(Scenario.model_validate(row.doc))
    world_ids = sorted({s.world for s in scenarios if isinstance(s.world, str)})
    worlds = await _latest(session, WorldRow, workspace_id, world_ids)
    rubric_ids = set(load_rubrics()) | set(
        (
            await session.execute(
                select(RubricRow.id).where(RubricRow.workspace_id == workspace_id)
            )
        ).scalars()
    )
    persona_ids = set(load_persona_library()) | set(
        (
            await session.execute(
                select(PersonaRow.id).where(PersonaRow.workspace_id == workspace_id)
            )
        ).scalars()
    )
    for scn in scenarios:
        if isinstance(scn.world, str):
            wrow = worlds.get(scn.world)
            if wrow is None:
                msg = f"world {scn.world!r} not found"
                errors.append({"scenario_id": scn.id, "code": "unknown_world", "message": msg})
                continue
            spec = WorldSpec.model_validate(wrow.doc)
        else:
            spec = scn.world
        for issue in validate_scenario(scn, spec, persona_ids=persona_ids, rubric_ids=rubric_ids):
            errors.append({"scenario_id": scn.id, "code": issue.code, "message": issue.message})
    reps = body.repetitions or suite.repetitions
    choices = await load_choices(session, workspace_id)
    run_cfg = effective_config(state.gateway_config, choices)
    version_model = agent_version_of(av)
    est = estimate_run_cost(
        scenarios,
        reps,
        run_cfg,
        agent_model=getattr(version_model.target, "model", None),
    )
    estimate = {"low": est.low, "expected": est.expected, "high": est.high}
    first = initial_repetitions(reps) if body.adaptive else reps  # adaptive: three to start
    if body.adaptive:
        low = estimate_run_cost(
            scenarios, first, run_cfg, agent_model=getattr(version_model.target, "model", None)
        ).low
        estimate = {"low": low, "expected": round(0.6 * est.expected), "high": est.high}
    warnings = list(est.warnings)
    if budget < est.low:
        warnings.append("budget is below the low cost estimate; the run may stop early")
    if dry_run:
        return {
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
            "episode_count": len(scenarios) * first,
            "estimate_usd_micros": estimate,
        }, 200
    if errors:
        raise ApiError(422, "validation_error", "the suite cannot run", errors)
    if enforce_daily:
        await enforce_daily_budget(session, state, workspace_id, budget)
    attack = is_attack_run(scenarios)
    if attack:
        await enforce_attack_run(
            session, state, workspace_id, version_model, scenarios,
            episodes=len(scenarios) * reps, budget_usd_micros=budget,
        )  # fmt: skip
    if body.baseline_run_id is not None:
        base = await session.get(Run, body.baseline_run_id)
        if base is None or base.workspace_id != workspace_id:
            raise not_found("run", body.baseline_run_id)
        check_baseline(None, base)
        if base.suite_id != suite.id:
            raise ApiError(422, "suite_mismatch", "baseline and run must use the same suite")
    seed = body.seed if body.seed is not None else random.Random().randrange(2**31)
    rid = run_id or new_id("run")
    manifest = RunManifest(
        run_id=rid,
        suite_id=suite.id,
        agent_version=version_model,
        scenario_versions={s.id: latest[s.id].version for s in scenarios},
        seed=seed,
        repetitions=reps,
        model_roles={k: v.model for k, v in run_cfg.llm.roles.items()},
        rubric_versions={},
        platform_version=platform_version(),
        budget_usd_micros=budget,
        created_at=datetime.now(UTC),
    )
    run = Run(
        id=rid,
        workspace_id=workspace_id,
        suite_id=suite.id,
        agent_version_id=av.id,
        manifest=manifest.model_dump(mode="json"),
        role_settings=resolved_roles(run_cfg),
        status="queued",
        repetitions=reps,
        seed=seed,
        world_versions={wid: w.version for wid, w in worlds.items()},
        budget_usd_micros=budget,
        purpose=purpose,
        finding_id=finding_id,
        attack=attack,
        baseline_of=body.baseline_run_id,
        adaptive=body.adaptive,
    )
    session.add(run)
    await session.flush()
    if attack:
        await audit(
            session, workspace_id, actor, "attack_run.created", "run", rid,
            {"agent_version_id": av.id, "episodes": len(scenarios) * reps, "purpose": purpose,
             "host": target_host(version_model.target)},
        )  # fmt: skip
    n = 0
    for scn in scenarios:
        for rep in range(first):
            session.add(
                Episode(
                    id=episode_ids[n] if episode_ids else new_id("ep"),
                    workspace_id=workspace_id,
                    run_id=rid,
                    scenario_id=scn.id,
                    scenario_version=latest[scn.id].version,
                    rep=rep,
                    rng_seed=derive_episode_seed(seed, scn.id, rep),
                )
            )
            n += 1
    await session.flush()
    out = await run_json(session, run, estimate=estimate)
    out["warnings"] = warnings
    return out, 201


async def set_run_status(session: AsyncSession, run: Run, action: str) -> None:
    """cancel | pause | resume, with the state machine of the spec (409 `run_not_active`)."""
    allowed = {
        "cancel": ("queued", "running", "paused"),
        "pause": ("queued", "running"),
        "resume": ("paused",),
    }[action]
    if run.status not in allowed:
        raise ApiError(409, "run_not_active", f"cannot {action} a run that is {run.status}")
    if action == "cancel":
        await session.execute(
            update(Episode)
            .where(Episode.run_id == run.id, Episode.status == "queued")
            .values(status="cancelled", finished_at=func.now())
        )
        run.status, run.finished_at = "cancelled", datetime.now(UTC)
    elif action == "pause":
        run.status = "paused"
    else:
        run.status = "running"


async def maybe_complete_run(
    session: AsyncSession, run_id: str, *, auto_cluster_min: int | None = None
) -> bool:
    """`done` once no episode is queued or leased (never overrides a cancelled run).

    Completing also reconciles the budget ledger with the journal. A worker killed between
    recording an effect and settling its reservation leaves a reservation nobody releases and
    spend below the recorded effect costs; with no episode left in flight, `reserved` is
    zero and `spent` is the sum of the episode costs (which the journal keeps atomically)."""
    res = await session.execute(
        text(
            "UPDATE runs SET status = 'done', finished_at = now() "
            "WHERE id = :r AND status IN ('queued', 'running') AND NOT EXISTS "
            "(SELECT 1 FROM episodes WHERE run_id = :r AND status IN ('queued', 'leased'))"
        ),
        {"r": run_id},
    )
    if res.rowcount != 1:  # type: ignore[attr-defined]
        return False
    await session.execute(
        text(
            "UPDATE runs SET reserved_usd_micros = 0, spent_usd_micros = "
            "(SELECT coalesce(sum(cost_usd_micros), 0) FROM episodes WHERE run_id = :r) "
            "WHERE id = :r"
        ),
        {"r": run_id},
    )
    from .findings import finalize_finding_run  # replay and verify runs update their finding
    from .stability import auto_quarantine_for_run

    await finalize_finding_run(session, run_id)
    await auto_quarantine_for_run(session, run_id)
    if auto_cluster_min is not None:
        failed = (
            await session.execute(
                text(
                    "SELECT count(*) FROM episodes WHERE run_id = :r AND status = 'done' "
                    "AND outcome = 'failed'"
                ),
                {"r": run_id},
            )
        ).scalar()
        if int(failed or 0) >= auto_cluster_min:  # failure clustering, P3-6
            await session.execute(
                text(
                    "INSERT INTO jobs (id, workspace_id, kind, payload) SELECT :id, workspace_id, "
                    "'cluster', CAST(:p AS jsonb) FROM runs WHERE id = :r"
                ),
                {"id": new_id("job"), "p": json.dumps({"run_id": run_id}), "r": run_id},
            )
    return True
