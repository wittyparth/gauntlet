"""Baselines, run comparison and trajectory diff (P3-1)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from gauntlet_core.eval import CompareReport, TrajectoryDiff
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from ..api_models import RunOut
from ..auth import AuthCtx
from ..deps import auth_ctx, db_session
from ..services.compare import (
    FindingsDeltaOut,
    compare_for_run,
    episode_diff,
    findings_delta,
    set_baseline,
)
from ..services.runs import run_json

router = APIRouter(prefix="/v1")


class BaselineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline_run_id: str


@router.put("/runs/{run_id}/baseline", response_model=RunOut)
async def put_baseline(
    run_id: str,
    body: BaselineIn,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    run = await set_baseline(s, auth.workspace_id, run_id, body.baseline_run_id)
    await s.commit()
    return await run_json(s, run)


@router.delete("/runs/{run_id}/baseline", response_model=RunOut)
async def delete_baseline(
    run_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    run = await set_baseline(s, auth.workspace_id, run_id, None)
    await s.commit()
    return await run_json(s, run)


@router.get("/runs/{run_id}/compare", response_model=CompareReport)
async def get_compare(
    run_id: str,
    baseline: str | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> CompareReport:
    """Compare against `baseline`, default the run's own `baseline_of`. Changes nothing."""
    return await compare_for_run(s, auth.workspace_id, run_id, baseline)


@router.get("/episodes/{episode_id}/diff", response_model=TrajectoryDiff)
async def get_episode_diff(
    episode_id: str,
    against: str,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> TrajectoryDiff:
    """Align this episode's trajectory with `against` (the baseline side)."""
    return await episode_diff(s, auth.workspace_id, episode_id, against)


@router.get("/runs/{run_id}/findings-delta", response_model=FindingsDeltaOut)
async def get_findings_delta(
    run_id: str,
    baseline: str | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> FindingsDeltaOut:
    """New security findings of the run versus its baseline (the CI gate's input)."""
    return await findings_delta(s, auth.workspace_id, run_id, baseline)
