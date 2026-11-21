"""Badge token management (authenticated) and the public SVG (CQ-R9)."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthCtx
from ..deps import AppState, auth_ctx, db_session, get_state
from ..services.badges import (
    GREY,
    BadgeOut,
    Metric,
    create_or_rotate,
    etag_of,
    render_svg,
    resolve_badge,
)

router = APIRouter(prefix="/v1")
public = APIRouter()

RATE_PER_MIN = 60
CACHE = "public, max-age=300"


@router.post("/agents/{agent_id}/badge", status_code=201, response_model=BadgeOut)
async def post_badge(
    agent_id: str,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> BadgeOut:
    """Creates the agent's badge token, or rotates it: the old url stops working at once."""
    return await create_or_rotate(
        s, auth.workspace_id, agent_id, state.settings.public_api_url, auth.key_name or auth.key_id
    )


def _svg(body: str, status: int = 200, *, cache: str = CACHE) -> Response:
    return Response(
        body,
        status_code=status,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": cache,
            "ETag": etag_of(body),
            "X-Content-Type-Options": "nosniff",
        },
    )


async def _limited(state: AppState, ip: str) -> bool:
    if state.redis is None:
        return False
    key = f"badge:rl:{ip}:{int(time.time() // 60)}"
    n = await state.redis.incr(key)
    await state.redis.expire(key, 120)
    return int(n) > RATE_PER_MIN


@public.get("/badge/{token}.svg", include_in_schema=False)
async def get_badge(
    token: str,
    request: Request,
    metric: Metric = "pass_rate",
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> Response:
    """Unauthenticated. Exposes a pass-rate string or a grade letter, nothing else."""
    ip = request.client.host if request.client else "unknown"
    if await _limited(state, ip):
        return _svg(render_svg("gauntlet", "rate limited", GREY), 429, cache="no-store")
    shown = await resolve_badge(s, token, metric)
    if shown is None:
        return _svg(render_svg("gauntlet", "invalid", GREY), 404, cache="no-store")
    body = render_svg(shown.label, shown.value, shown.colour)
    if request.headers.get("if-none-match") == etag_of(body):
        return Response(status_code=304, headers={"ETag": etag_of(body), "Cache-Control": CACHE})
    return _svg(body)
