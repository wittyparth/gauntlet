"""Audit log reads and chain verification."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthCtx
from ..db.sec_models import AuditLog
from ..deps import auth_ctx, db_session
from ..services.audit import ChainReport, verify_chain

router = APIRouter(prefix="/v1")


class AuditRow(BaseModel):
    id: str
    ts: str
    actor: str
    action: str
    subject_type: str
    subject_id: str
    detail: dict[str, Any]
    hash: str


class AuditList(BaseModel):
    items: list[AuditRow]


@router.get("/audit", response_model=AuditList)
async def list_audit(
    action: str | None = None,
    subject_type: str | None = None,
    subject_id: str | None = None,
    from_: datetime | None = None,
    to: datetime | None = None,
    limit: int = 200,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    q = select(AuditLog).where(AuditLog.workspace_id == auth.workspace_id)
    if action:
        q = q.where(AuditLog.action == action)
    if subject_type:
        q = q.where(AuditLog.subject_type == subject_type)
    if subject_id:
        q = q.where(AuditLog.subject_id == subject_id)
    if from_:
        q = q.where(AuditLog.ts >= from_)
    if to:
        q = q.where(AuditLog.ts <= to)
    rows = (
        await s.execute(q.order_by(AuditLog.seq.desc()).limit(max(1, min(limit, 1000))))
    ).scalars()
    return {
        "items": [
            {
                "id": r.id, "ts": r.ts.isoformat(), "actor": r.actor, "action": r.action,
                "subject_type": r.subject_type, "subject_id": r.subject_id, "detail": r.detail,
                "hash": r.hash,
            }
            for r in rows
        ]
    }  # fmt: skip


@router.get("/audit/verify", response_model=ChainReport)
async def audit_verify(
    auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> ChainReport:
    return await verify_chain(s, auth.workspace_id)
