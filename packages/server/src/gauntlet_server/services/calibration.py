"""Calibration jobs and drift (P3-5, CQ-R2): measure the judges against the golden set, store the
outcome in `calibrations`, and keep `effective_rubric` honest when models change."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from gauntlet_core.ids import new_id
from gauntlet_core.judges import CalibrationReport, GoldenItem, calibrate
from gauntlet_core.llm.types import LLMResult
from gauntlet_core.schema import Rubric
from gauntlet_core.stats import Agreement
from gauntlet_core.world import build_trajectory, build_world
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Episode
from ..db.review_models import Calibration
from ..deps import AppState
from ..errors import ApiError, not_found
from ..jobs import load_episode_inputs
from ..models_gateway import gateway_for_roles
from ..stores.jobs import PgJobQueue
from .audit import audit
from .calibration_state import JUDGE_ROLES, effective_rubric, judge_models
from .golden import golden_items, readiness
from .jobs import JobContext, handler
from .model_settings import effective_config, load_choices, resolved_roles
from .reports import _events

__all__ = [
    "CalibrateIn",
    "CalibrateOut",
    "CalibrationOut",
    "DriftOut",
    "check_drift",
    "check_drift_all",
    "create_calibration",
    "current_models",
    "run_calibration",
]

log = logging.getLogger("gauntlet.calibration")


class CalibrateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int | None = None
    taus: list[float] | None = None


class CalibrateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    calibration_id: str
    job_id: str


class CalibrationOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    rubric_id: str
    rubric_version: int
    judge_models: dict[str, Any]
    status: str
    result: dict[str, Any] | None
    golden_count: int
    gating_allowed: bool
    threshold: float | None
    stale: bool
    error: str | None
    cost_usd_micros: int
    created_at: str
    finished_at: str | None


class DriftOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stale: list[str]
    enqueued: list[str]  # job ids of the re-calibrations
    skipped: list[str]  # stale calibrations whose golden set is below gating size


def calibration_json(c: Calibration) -> dict[str, Any]:
    return {
        "id": c.id,
        "rubric_id": c.rubric_id,
        "rubric_version": c.rubric_version,
        "judge_models": c.judge_models,
        "status": c.status,
        "result": c.result,
        "golden_count": c.golden_count,
        "gating_allowed": c.gating_allowed,
        "threshold": c.threshold,
        "stale": c.stale,
        "error": c.error,
        "cost_usd_micros": c.cost_usd_micros,
        "created_at": c.created_at.isoformat(),
        "finished_at": c.finished_at.isoformat() if c.finished_at else None,
    }


async def current_models(state: AppState, s: AsyncSession, ws: str) -> dict[str, str]:
    cfg = effective_config(state.gateway_config, await load_choices(s, ws))
    return judge_models(resolved_roles(cfg))


async def create_calibration(
    state: AppState, s: AsyncSession, ws: str, rubric_id: str, body: CalibrateIn, actor: str
) -> CalibrateOut:
    try:
        rubric = await effective_rubric(s, ws, rubric_id, body.version)
    except LookupError as e:
        raise not_found("rubric", rubric_id) from e
    items = await golden_items(s, ws, rubric_id, rubric.version)
    if not items:
        raise ApiError(422, "no_golden_items", "this rubric version has no golden items yet")
    cal = Calibration(
        id=new_id("cal"),
        workspace_id=ws,
        rubric_id=rubric_id,
        rubric_version=rubric.version,
        judge_models=await current_models(state, s, ws),
        status="queued",
        golden_count=len(items),
    )
    s.add(cal)
    await s.flush()
    job_id = await PgJobQueue(state.sm).enqueue(
        ws, "calibrate", {"calibration_id": cal.id, "taus": body.taus}, session=s
    )
    detail = {"rubric_id": rubric_id, "version": rubric.version, "golden": len(items)}
    await audit(s, ws, actor, "calibration.requested", "calibration", cal.id, detail)
    await s.commit()
    return CalibrateOut(calibration_id=cal.id, job_id=job_id)


class _Metered:
    """Gateway view that sums spend per role (calibration cost goes on its own row)."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.usd: dict[str, int] = defaultdict(int)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    async def complete(self, role: str, *args: Any, **kw: Any) -> LLMResult:
        res: LLMResult = await self.inner.complete(role, *args, **kw)
        self.usd[role] += res.cost.usd_micros
        return res


def _agreement_json(a: Agreement | None) -> dict[str, Any] | None:
    if a is None:
        return None
    return {
        "n": a.n,
        "accuracy": a.accuracy,
        "precision_fail": a.precision,
        "recall_fail": a.recall,
        "kappa": a.kappa,
        "kappa_ci": [a.kappa_low, a.kappa_high],
    }


def report_json(rep: CalibrationReport, usd: dict[str, int]) -> dict[str, Any]:
    n = max(rep.n, 1)
    chosen = next((p for p in rep.points if p.tau == rep.threshold), None)
    return {
        "n": rep.n,
        "n_pass": rep.n_nonfail,
        "n_fail": rep.n_fail,
        "small": _agreement_json(rep.small),
        "strong": _agreement_json(rep.strong),
        "cascade_by_tau": [
            {
                "tau": p.tau,
                "kappa": p.agreement.kappa if p.agreement else None,
                "escalation_rate": p.escalation_rate,
                "cost_per_verdict_usd_micros": p.cost_per_verdict_usd_micros,
            }
            for p in rep.points
        ],
        "chosen_tau": rep.threshold,
        "escalation_rate": chosen.escalation_rate if chosen else None,
        "cost_per_verdict_usd_micros": {
            "small": usd.get("judge_small", 0) / n,
            "strong": usd.get("judge_strong", 0) / n,
            "cascade": chosen.cost_per_verdict_usd_micros if chosen else None,
        },
        "gating_allowed": rep.gating_allowed,
        "reasons": [] if rep.gating_reason == "ok" else rep.gating_reason.split("; "),
    }


async def run_calibration(
    state: AppState, calibration_id: str, taus: list[float] | None
) -> dict[str, Any]:
    """Idempotent: everything lands on the calibration row `calibration_id` itself."""
    async with state.sm() as s:
        cal = await s.get(Calibration, calibration_id)
        if cal is None:
            raise LookupError(f"calibration {calibration_id} not found")
        ws, rubric_id, version = cal.workspace_id, cal.rubric_id, cal.rubric_version
        cal.status, cal.error = "running", None
        await s.commit()
        rubric = await _document(s, ws, rubric_id, version)
        items = await golden_items(s, ws, rubric_id, version)
        golden: list[GoldenItem] = []
        policy = ""
        for it in items:
            ep = await s.get(Episode, it.episode_id)
            if ep is None:
                continue
            inputs = await load_episode_inputs(s, it.episode_id)
            built = build_world(inputs.world, inputs.scenario.world_overrides, int(ep.rng_seed))
            traj = build_trajectory(
                it.episode_id, inputs.scenario, await _events(s, it.episode_id), built
            )
            golden.append(GoldenItem(it.episode_id, traj, it.result))
            policy = policy or inputs.manifest.agent_version.profile.policies_text
        roles = resolved_roles(effective_config(state.gateway_config, await load_choices(s, ws)))
    gateway = _Metered(gateway_for_roles(state.gateway, roles))
    kw: dict[str, Any] = {"taus": taus} if taus else {}
    rep = await calibrate(rubric, golden, gateway, policy_text=policy, **kw)  # type: ignore[arg-type]
    result = report_json(rep, dict(gateway.usd))
    async with state.sm() as s:
        cal = await s.get(Calibration, calibration_id)
        assert cal is not None
        cal.status, cal.result = "done", result
        cal.gating_allowed = rep.gating_allowed
        cal.threshold = min(rep.threshold, 1.0)
        cal.golden_count = len(golden)
        cal.judge_models = judge_models(roles)
        cal.cost_usd_micros = sum(gateway.usd.values())
        cal.finished_at = datetime.now(UTC)
        await s.commit()
    return {"calibration_id": calibration_id, "gating_allowed": rep.gating_allowed}


async def _document(s: AsyncSession, ws: str, rubric_id: str, version: int) -> Rubric:
    """The stored rubric document itself (calibrated values are not baked in)."""
    from gauntlet_core.eval import load_rubrics

    from ..db.models import Rubric as RubricRow

    row = await s.get(RubricRow, (rubric_id, version))
    if row is not None and row.workspace_id == ws:
        return Rubric.model_validate(row.doc)
    lib = load_rubrics().get(rubric_id)
    if lib is None:
        raise LookupError(f"rubric {rubric_id} v{version} not found")
    return lib


@handler("calibrate")
async def calibrate_job(ctx: JobContext) -> dict[str, Any]:
    try:
        return await run_calibration(
            ctx.state, str(ctx.payload["calibration_id"]), ctx.payload.get("taus")
        )
    except Exception as e:
        # the final attempt leaves the row failed with the reason; earlier ones retry
        from ..stores.jobs import MAX_ATTEMPTS

        if ctx.attempts >= MAX_ATTEMPTS:
            async with ctx.state.sm() as s:
                cal = await s.get(Calibration, str(ctx.payload["calibration_id"]))
                if cal is not None:
                    cal.status, cal.error = "failed", f"{type(e).__name__}: {e}"
                    cal.finished_at = datetime.now(UTC)
                    await s.commit()
        raise


async def check_drift(state: AppState, s: AsyncSession, ws: str, actor: str = "system") -> DriftOut:
    """Mark calibrations stale when the judge models changed since they were measured, and
    queue a re-calibration for each whose golden set can still gate."""
    models = await current_models(state, s, ws)
    rows = (
        (
            await s.execute(
                select(Calibration)
                .where(Calibration.workspace_id == ws, Calibration.status == "done")
                .order_by(Calibration.created_at.desc(), Calibration.id.desc())
            )
        )
        .scalars()
        .all()
    )
    latest: dict[tuple[str, int], Calibration] = {}
    for c in rows:
        latest.setdefault((c.rubric_id, c.rubric_version), c)
    out = DriftOut(stale=[], enqueued=[], skipped=[])
    for (rubric_id, version), c in latest.items():
        if c.stale or {r: c.judge_models.get(r) for r in JUDGE_ROLES} == {
            r: models.get(r) for r in JUDGE_ROLES
        }:
            continue
        c.stale = True
        out.stale.append(c.id)
        items = await golden_items(s, ws, rubric_id, version)
        if not readiness(items)[0]:
            out.skipped.append(c.id)
            continue
        new = Calibration(
            id=new_id("cal"),
            workspace_id=ws,
            rubric_id=rubric_id,
            rubric_version=version,
            judge_models=models,
            status="queued",
            golden_count=len(items),
        )
        s.add(new)
        await s.flush()
        out.enqueued.append(
            await PgJobQueue(state.sm).enqueue(
                ws, "calibrate", {"calibration_id": new.id, "taus": None}, session=s
            )
        )
        await audit(s, ws, actor, "calibration.drift", "calibration", c.id,
                    {"models": models, "recalibration": new.id})  # fmt: skip
    await s.commit()
    return out


async def check_drift_all(state: AppState) -> None:
    from sqlalchemy import text

    async with state.sm() as s:
        workspaces = list(
            (await s.execute(text("SELECT DISTINCT workspace_id FROM calibrations"))).scalars()
        )
    for ws in workspaces:
        async with state.sm() as s:
            await check_drift(state, s, ws)
