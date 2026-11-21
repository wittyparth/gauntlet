"""Security posture and coverage for an agent version."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Response
from gauntlet_core.security.posture import render_markdown
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthCtx
from ..deps import auth_ctx, db_session
from ..services.posture import CoverageOut, PostureOut, build_coverage, build_posture

router = APIRouter(prefix="/v1")


@router.get("/agents/{agent_id}/versions/{version_id}/posture", response_model=PostureOut | str)
async def posture(
    agent_id: str,
    version_id: str,
    compare_to: str | None = None,
    format: Literal["json", "md"] = "json",
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> Any:
    """JSON by default; `format=md` returns the same data as a markdown report."""
    data = await build_posture(s, auth.workspace_id, agent_id, version_id, compare_to)
    out = PostureOut.model_validate(data)
    if format == "md":
        return Response(render_markdown(out), media_type="text/markdown")
    return out


@router.get("/agents/{agent_id}/versions/{version_id}/coverage", response_model=CoverageOut)
async def coverage(
    agent_id: str,
    version_id: str,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    return await build_coverage(s, auth.workspace_id, agent_id, version_id)
