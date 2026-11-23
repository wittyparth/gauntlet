"""SLOs with error budgets (P5-7)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthCtx
from ..deps import auth_ctx, db_session
from ..services.slo import (
    SloIn,
    SloOut,
    SloPatch,
    SloStatusOut,
    create_slo,
    delete_slo,
    evaluate_slo,
    get_slo,
    list_slos,
    update_slo,
)

router = APIRouter(prefix="/v1/slos")


def _actor(a: AuthCtx) -> str:
    return a.key_name or a.key_id


@router.post("", status_code=201, response_model=SloOut)
async def post_slo(
    body: SloIn, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> SloOut:
    return await create_slo(s, auth.workspace_id, body, _actor(auth))


@router.get("", response_model=list[SloOut])
async def get_slos(
    auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> list[SloOut]:
    return await list_slos(s, auth.workspace_id)


@router.get("/{slo_id}", response_model=SloOut)
async def get_one(
    slo_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> SloOut:
    return await get_slo(s, auth.workspace_id, slo_id)


@router.patch("/{slo_id}", response_model=SloOut)
async def patch_slo(
    slo_id: str,
    body: SloPatch,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> SloOut:
    return await update_slo(s, auth.workspace_id, slo_id, body, _actor(auth))


@router.delete("/{slo_id}", status_code=204)
async def remove_slo(
    slo_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> None:
    await delete_slo(s, auth.workspace_id, slo_id, _actor(auth))


@router.get("/{slo_id}/status", response_model=SloStatusOut)
async def get_status(
    slo_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> SloStatusOut:
    """Compliance, error budget and burn rates over the window; `unknown` when it has no
    samples. A breach needs the interval to exclude the objective."""
    return await evaluate_slo(s, auth.workspace_id, slo_id)
