"""Agent version scorecard (P3-8)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthCtx
from ..db.models import AgentVersion
from ..deps import AppState, auth_ctx, db_session, get_state
from ..services.scorecard import Scorecard, build_scorecard
from .core import _version

router = APIRouter(prefix="/v1")


@router.get("/agents/{agent_id}/versions/{version_id}/scorecard", response_model=Scorecard)
async def get_scorecard(
    agent_id: str,
    version_id: str,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> Scorecard:
    data = await build_scorecard(
        s, auth.workspace_id, agent_id, version_id, state.settings.public_api_url
    )
    v = await s.get(AgentVersion, version_id)
    assert v is not None
    return Scorecard(**data.model_dump(), agent_version=_version(v))  # type: ignore[arg-type]
