"""Gateway decisions, stats and approvals (P4-2)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthCtx
from ..deps import auth_ctx, db_session
from ..services.gateway import (
    AcceptedOut,
    ApprovalIn,
    ApprovalOut,
    DecideIn,
    DecisionsPage,
    IngestIn,
    StatsOut,
    Status,
    create_approval,
    decide_approval,
    gateway_stats,
    get_approval,
    ingest_decisions,
    list_approvals,
    list_decisions,
)

router = APIRouter(prefix="/v1/gateway")


def _actor(auth: AuthCtx) -> str:
    return auth.key_name or auth.key_id


@router.post("/decisions", status_code=202, response_model=AcceptedOut)
async def post_decisions(
    body: IngestIn, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> AcceptedOut:
    """A batch of up to 500 records from an SDK sink. Idempotent on the record id."""
    return await ingest_decisions(s, auth.workspace_id, body)


@router.get("/decisions", response_model=DecisionsPage)
async def get_decisions(
    policy_id: str | None = None,
    action: str | None = None,
    tool: str | None = None,
    rule_id: str | None = None,
    mode: str | None = None,
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    enforced: bool | None = None,
    limit: int = 50,
    cursor: str | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> DecisionsPage:
    return await list_decisions(
        s, auth.workspace_id, policy_id=policy_id, action=action, tool=tool, rule_id=rule_id,
        mode=mode, from_ts=from_ts, to_ts=to_ts, enforced=enforced, limit=limit, cursor=cursor,
    )  # fmt: skip


@router.get("/stats", response_model=StatsOut)
async def get_stats(
    window: str = "1h", auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> StatsOut:
    return await gateway_stats(s, auth.workspace_id, window)


@router.post("/approvals", status_code=201, response_model=ApprovalOut)
async def post_approval(
    body: ApprovalIn, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> ApprovalOut:
    return await create_approval(s, auth.workspace_id, body, _actor(auth))


@router.get("/approvals", response_model=list[ApprovalOut])
async def get_approvals(
    status: Status | None = None,
    limit: int = 50,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> list[ApprovalOut]:
    return await list_approvals(s, auth.workspace_id, status, limit)


@router.get("/approvals/{approval_id}", response_model=ApprovalOut)
async def get_one_approval(
    approval_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> ApprovalOut:
    return await get_approval(s, auth.workspace_id, approval_id)


@router.post("/approvals/{approval_id}/decide", response_model=ApprovalOut)
async def post_decide(
    approval_id: str,
    body: DecideIn,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> ApprovalOut:
    return await decide_approval(s, auth.workspace_id, approval_id, body, _actor(auth))
