"""Readiness review of an agent version (P5-7). Read-only."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthCtx
from ..deps import auth_ctx, db_session
from ..services.readiness import ReadinessOut, build_readiness

router = APIRouter(prefix="/v1")


@router.get("/agents/{agent_id}/versions/{version_id}/readiness", response_model=ReadinessOut)
async def get_readiness(
    agent_id: str,
    version_id: str,
    baseline: str | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> ReadinessOut:
    """Go, conditional or no-go with blockers and unverified claims, each criterion with its
    interval and the runs behind it. Wording is evidence for a decision, not a certification."""
    return await build_readiness(s, auth.workspace_id, agent_id, version_id, baseline)
