"""Human review queue, labels and blind items (P3-5)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthCtx
from ..deps import auth_ctx, db_session
from ..services.review import (
    ItemOut,
    LabelIn,
    LabelOut,
    QueueOut,
    get_item,
    put_label,
    review_queue,
)

router = APIRouter(prefix="/v1")


def labeler_of(auth: AuthCtx) -> str:
    """The API key name (no user accounts in the MVP), else its id."""
    return auth.key_name or auth.key_id


@router.get("/review/queue", response_model=QueueOut)
async def get_queue(
    rubric: str,
    limit: int = 20,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> QueueOut:
    return await review_queue(
        s, auth.workspace_id, rubric, labeler_of(auth), min(max(limit, 1), 100)
    )


@router.post("/review/labels", response_model=LabelOut)
async def post_label(
    body: LabelIn, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> LabelOut:
    return await put_label(s, auth.workspace_id, labeler_of(auth), body)


@router.get("/review/items/{episode_id}/{rubric_id}", response_model=ItemOut)
async def get_review_item(
    episode_id: str,
    rubric_id: str,
    reveal: bool = False,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> ItemOut:
    """Blind by default; `reveal=true` shows the judge verdict only after the caller labelled."""
    return await get_item(
        s, auth.workspace_id, episode_id, rubric_id, labeler_of(auth), reveal=reveal
    )
