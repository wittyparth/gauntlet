"""Production conversations (P5-1): list, detail, evaluate, stats."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthCtx
from ..deps import AppState, auth_ctx, db_session, get_state
from ..services.production import (
    ConversationDetail,
    ConversationsPage,
    EvalStarted,
    EvaluateIn,
    ProductionStats,
    enqueue_evaluate,
    get_conversation,
    list_conversations,
    production_stats,
)

router = APIRouter(prefix="/v1/production")


@router.get("/conversations", response_model=ConversationsPage)
async def get_conversations(
    agent_id: str | None = None,
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    signal: str | None = None,
    q: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    """`signal` names a counter (`tool_errors`, `unmapped_spans`, ...) that must be above zero;
    `q` searches the redacted text."""
    return await list_conversations(
        s, auth.workspace_id, agent_id=agent_id, from_ts=from_ts, to_ts=to_ts, signal=signal,
        q=q, limit=limit, cursor=cursor,
    )  # fmt: skip


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_one(
    conversation_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    return await get_conversation(s, auth.workspace_id, conversation_id)


@router.post(
    "/conversations/{conversation_id}/evaluate", status_code=202, response_model=EvalStarted
)
async def post_evaluate(
    conversation_id: str,
    body: EvaluateIn | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> EvalStarted:
    """Queues a job that runs detectors and checks over the conversation (no world: world
    checks come back `na`) and records the verdicts in a `purpose=import` run."""
    return await enqueue_evaluate(
        state, s, auth.workspace_id, conversation_id, body or EvaluateIn(),
        auth.key_name or auth.key_id,
    )  # fmt: skip


@router.get("/stats", response_model=ProductionStats)
async def get_stats(
    window_days: int = 7, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> ProductionStats:
    return await production_stats(s, auth.workspace_id, max(1, min(window_days, 365)))
