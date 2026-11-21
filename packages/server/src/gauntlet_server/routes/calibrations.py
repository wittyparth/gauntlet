"""Golden sets, calibration and drift (P3-5)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthCtx
from ..db.review_models import Calibration
from ..deps import AppState, auth_ctx, db_session, get_state
from ..errors import not_found
from ..services.calibration import (
    CalibrateIn,
    CalibrateOut,
    CalibrationOut,
    DriftOut,
    calibration_json,
    check_drift,
    create_calibration,
)
from ..services.golden import GoldenIn, GoldenOut, GoldenSummary, golden_summary, mark_golden

router = APIRouter(prefix="/v1")


class CalibrationList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[CalibrationOut]


@router.post("/rubrics/{rubric_id}/golden", response_model=GoldenOut)
async def post_golden(
    rubric_id: str,
    body: GoldenIn,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> GoldenOut:
    return await mark_golden(s, auth.workspace_id, rubric_id, body.episode_ids)


@router.get("/rubrics/{rubric_id}/golden", response_model=GoldenSummary)
async def get_golden(
    rubric_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> GoldenSummary:
    return await golden_summary(s, auth.workspace_id, rubric_id)


@router.post("/rubrics/{rubric_id}/calibrate", status_code=202, response_model=CalibrateOut)
async def post_calibrate(
    rubric_id: str,
    body: CalibrateIn | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> CalibrateOut:
    return await create_calibration(
        state, s, auth.workspace_id, rubric_id, body or CalibrateIn(), auth.key_name or auth.key_id
    )


@router.get("/rubrics/{rubric_id}/calibrations", response_model=CalibrationList)
async def list_calibrations(
    rubric_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    rows = (
        (
            await s.execute(
                select(Calibration)
                .where(
                    Calibration.workspace_id == auth.workspace_id,
                    Calibration.rubric_id == rubric_id,
                )
                .order_by(Calibration.created_at.desc(), Calibration.id.desc())
                .limit(100)
            )
        )
        .scalars()
        .all()
    )
    return {"items": [calibration_json(c) for c in rows]}


@router.get("/calibrations/{calibration_id}", response_model=CalibrationOut)
async def get_calibration(
    calibration_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    c = await s.get(Calibration, calibration_id)
    if c is None or c.workspace_id != auth.workspace_id:
        raise not_found("calibration", calibration_id)
    return calibration_json(c)


@router.post("/calibrations/check-drift", response_model=DriftOut)
async def post_check_drift(
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> DriftOut:
    return await check_drift(state, s, auth.workspace_id, auth.key_name or auth.key_id)
