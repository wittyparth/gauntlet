"""Scheduled runs (P5-7). No schedule exists by default; cron is five fields in UTC."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthCtx
from ..deps import AppState, auth_ctx, db_session, get_state
from ..services.schedules import (
    FireOut,
    ScheduleIn,
    ScheduleOut,
    SchedulePatch,
    create_schedule,
    delete_schedule,
    fire_now,
    list_schedules,
    update_schedule,
)

router = APIRouter(prefix="/v1/schedules")


def _actor(a: AuthCtx) -> str:
    return a.key_name or a.key_id


@router.post("", status_code=201, response_model=ScheduleOut)
async def post_schedule(
    body: ScheduleIn, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> ScheduleOut:
    return await create_schedule(s, auth.workspace_id, body, _actor(auth))


@router.get("", response_model=list[ScheduleOut])
async def get_schedules(
    auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> list[ScheduleOut]:
    return await list_schedules(s, auth.workspace_id)


@router.patch("/{schedule_id}", response_model=ScheduleOut)
async def patch_schedule(
    schedule_id: str,
    body: SchedulePatch,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> ScheduleOut:
    return await update_schedule(s, auth.workspace_id, schedule_id, body, _actor(auth))


@router.delete("/{schedule_id}", status_code=204)
async def remove_schedule(
    schedule_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> None:
    await delete_schedule(s, auth.workspace_id, schedule_id, _actor(auth))


@router.post("/{schedule_id}/run-now", response_model=FireOut)
async def run_now(
    schedule_id: str, auth: AuthCtx = Depends(auth_ctx), state: AppState = Depends(get_state)
) -> FireOut:
    """Starts the schedule's run now (budget checks apply); the next scheduled fire is kept."""
    return await fire_now(state, auth.workspace_id, schedule_id, _actor(auth))
