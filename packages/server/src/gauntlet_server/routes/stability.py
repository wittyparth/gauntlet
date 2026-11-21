"""Scenario quarantine and stability (P3-2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthCtx
from ..deps import auth_ctx, db_session
from ..services.stability import QuarantineOut, StabilityOut, set_quarantine, stability

router = APIRouter(prefix="/v1")


class QuarantineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    on: bool
    reason: str = ""


@router.post("/scenarios/{scenario_id}/quarantine", response_model=QuarantineOut)
async def post_quarantine(
    scenario_id: str,
    body: QuarantineIn,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> QuarantineOut:
    """Quarantined scenarios keep running but leave the headline rate, pass^k, comparisons
    and gates."""
    out = await set_quarantine(
        s, auth.workspace_id, scenario_id, body.on, body.reason, auth.key_name or auth.key_id
    )
    await s.commit()
    return out


@router.get("/scenarios/{scenario_id}/stability", response_model=StabilityOut)
async def get_stability(
    scenario_id: str,
    agent_version_id: str | None = None,
    limit: int = 10,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> StabilityOut:
    return await stability(s, auth.workspace_id, scenario_id, agent_version_id, min(limit, 50))
