"""Ownership verification of remote targets."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthCtx
from ..db.sec_models import TargetVerification
from ..deps import AppState, auth_ctx, db_session, get_state
from ..errors import not_found
from ..services.audit import audit
from ..services.ownership import check_verification, instructions, request_verification

router = APIRouter(prefix="/v1")


class VerificationCreate(BaseModel):
    host: str
    method: Literal["dns", "http"]


class VerificationOut(BaseModel):
    id: str
    host: str
    method: str
    status: str
    token: str
    instructions: dict[str, str]
    verified_at: str | None = None
    expires_at: str | None = None
    last_checked_at: str | None = None
    detail: str | None = None


class VerificationList(BaseModel):
    items: list[VerificationOut]


def _out(v: TargetVerification) -> dict[str, Any]:
    status = v.status
    if status == "verified" and v.expires_at is not None and v.expires_at < datetime.now(UTC):
        status = "expired"
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    return {
        "id": v.id, "host": v.host, "method": v.method, "status": status, "token": v.token,
        "instructions": instructions(v), "verified_at": iso(v.verified_at),
        "expires_at": iso(v.expires_at), "last_checked_at": iso(v.last_checked_at),
        "detail": v.detail,
    }  # fmt: skip


async def _get(s: AsyncSession, auth: AuthCtx, vid: str) -> TargetVerification:
    v = await s.get(TargetVerification, vid)
    if v is None or v.workspace_id != auth.workspace_id:
        raise not_found("verification", vid)
    return v


@router.post("/targets/verifications", status_code=201, response_model=VerificationOut)
async def create_verification(
    body: VerificationCreate,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    v = await request_verification(s, auth.workspace_id, body.host, body.method)
    await audit(
        s, auth.workspace_id, auth.key_name or auth.key_id, "target.verification_requested",
        "target", v.host, {"host": v.host, "method": v.method},
    )  # fmt: skip
    await s.commit()
    return _out(v)


@router.post("/targets/verifications/{vid}/check", response_model=VerificationOut)
async def check(
    vid: str,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> dict[str, Any]:
    v = await check_verification(s, await _get(s, auth, vid), state.settings)
    action = "target.verified" if v.status == "verified" else "target.verification_failed"
    await audit(
        s, auth.workspace_id, auth.key_name or auth.key_id, action, "target", v.host,
        {"host": v.host, "method": v.method},
    )  # fmt: skip
    await s.commit()
    return _out(v)


@router.get("/targets/verifications", response_model=VerificationList)
async def list_verifications(
    auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    rows = (
        await s.execute(
            select(TargetVerification)
            .where(TargetVerification.workspace_id == auth.workspace_id)
            .order_by(TargetVerification.created_at.desc())
        )
    ).scalars()
    return {"items": [_out(v) for v in rows]}


@router.delete("/targets/verifications/{vid}", status_code=204)
async def delete_verification(
    vid: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> None:
    await s.delete(await _get(s, auth, vid))
    await s.commit()
