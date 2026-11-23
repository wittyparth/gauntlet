"""Change impact: which scenarios to re-run after a change (P5-7). Read-only."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthCtx
from ..deps import auth_ctx, db_session
from ..services.impact import ImpactIn, ImpactOut, impact_for_versions

router = APIRouter(prefix="/v1")


@router.post("/impact", response_model=ImpactOut)
async def post_impact(
    body: ImpactIn, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> ImpactOut:
    """Conservative selection with a reason per scenario; `full_run` is set when the change
    class is unknown. Nothing is created: the suggested suite is a list of ids."""
    return await impact_for_versions(s, auth.workspace_id, body)
