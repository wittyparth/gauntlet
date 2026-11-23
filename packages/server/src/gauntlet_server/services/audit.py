"""Append-only, hash-chained audit log (P2-4). `detail` carries ids, counts and hosts only,
never payload text or secrets. Appends take a per-workspace advisory lock, so the chain is
linear; a database trigger refuses UPDATE and DELETE."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from gauntlet_core.audit_chain import GENESIS, row_hash
from gauntlet_core.ids import new_id
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.sec_models import AuditLog

__all__ = ["GENESIS", "ChainReport", "audit", "row_hash", "verify_chain"]


class ChainReport(BaseModel):
    ok: bool
    checked: int
    first_bad_id: str | None = None


async def audit(
    session: AsyncSession,
    workspace_id: str,
    actor: str,
    action: str,
    subject_type: str,
    subject_id: str,
    detail: dict[str, Any] | None = None,
) -> None:
    """Append one row inside the caller's transaction (the lock lasts until it commits)."""
    detail_doc: dict[str, Any] = json.loads(json.dumps(detail or {}))
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:w))"), {"w": f"audit:{workspace_id}"}
    )
    prev = (
        await session.execute(
            select(AuditLog.hash)
            .where(AuditLog.workspace_id == workspace_id)
            .order_by(AuditLog.seq.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    prev = prev or GENESIS
    rid, ts = new_id("aud"), datetime.now(UTC)
    h = row_hash(
        prev, id=rid, workspace_id=workspace_id, ts=ts, actor=actor, action=action,
        subject_type=subject_type, subject_id=subject_id, detail=detail_doc,
    )  # fmt: skip
    session.add(
        AuditLog(
            id=rid, workspace_id=workspace_id, ts=ts, actor=actor, action=action,
            subject_type=subject_type, subject_id=subject_id, detail=detail_doc,
            prev_hash=prev, hash=h,
        )
    )  # fmt: skip
    await session.flush()


async def verify_chain(session: AsyncSession, workspace_id: str) -> ChainReport:
    rows = (
        await session.execute(
            select(AuditLog).where(AuditLog.workspace_id == workspace_id).order_by(AuditLog.seq)
        )
    ).scalars()
    prev, n = GENESIS, 0
    for r in rows:
        want = row_hash(
            prev, id=r.id, workspace_id=r.workspace_id, ts=r.ts, actor=r.actor, action=r.action,
            subject_type=r.subject_type, subject_id=r.subject_id, detail=r.detail,
        )  # fmt: skip
        if r.prev_hash != prev or r.hash != want:
            return ChainReport(ok=False, checked=n, first_bad_id=r.id)
        prev, n = r.hash, n + 1
    return ChainReport(ok=True, checked=n)
