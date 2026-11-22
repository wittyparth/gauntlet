"""Failure mining over production conversations (P5-2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthCtx
from ..deps import AppState, auth_ctx, db_session, get_state
from ..services.mining import (
    CandidateDetail,
    CandidateOut,
    CandidatesPage,
    ConvertStarted,
    MineIn,
    MiningRunOut,
    MiningStarted,
    dismiss_candidate,
    enqueue_convert,
    enqueue_mine,
    get_candidate,
    get_mining_run,
    list_candidates,
)

router = APIRouter(prefix="/v1/production")


def _actor(auth: AuthCtx) -> str:
    return auth.key_name or auth.key_id


@router.post("/mine", status_code=202, response_model=MiningStarted)
async def post_mine(
    body: MineIn,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> MiningStarted:
    """Queues a mining run over an agent's conversations. A budget is required: judge and
    cluster-naming calls stop when it is spent."""
    return await enqueue_mine(state, s, auth.workspace_id, body, _actor(auth))


@router.get("/mine/{mining_run_id}", response_model=MiningRunOut)
async def get_run(
    mining_run_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> MiningRunOut:
    return await get_mining_run(s, auth.workspace_id, mining_run_id)


@router.get("/candidates", response_model=CandidatesPage)
async def get_candidates(
    mining_run_id: str | None = None,
    status: str | None = None,
    cluster: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> CandidatesPage:
    """Ranked by score, highest first."""
    return await list_candidates(
        s, auth.workspace_id, mining_run_id=mining_run_id, status=status, cluster=cluster,
        limit=limit, cursor=cursor,
    )  # fmt: skip


@router.get("/candidates/{candidate_id}", response_model=CandidateDetail)
async def get_one(
    candidate_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> CandidateDetail:
    return await get_candidate(s, auth.workspace_id, candidate_id)


@router.post("/candidates/{candidate_id}/convert", status_code=202, response_model=ConvertStarted)
async def post_convert(
    candidate_id: str,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> ConvertStarted:
    """Queues the conversion to a draft scenario. It fails closed on any personal data left."""
    return await enqueue_convert(state, s, auth.workspace_id, candidate_id, _actor(auth))


@router.post("/candidates/{candidate_id}/dismiss", response_model=CandidateOut)
async def post_dismiss(
    candidate_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> CandidateOut:
    return await dismiss_candidate(s, auth.workspace_id, candidate_id, _actor(auth))
