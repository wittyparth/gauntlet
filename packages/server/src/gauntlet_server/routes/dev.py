"""`POST /v1/dev/seed`, only when GAUNTLET_ENV=dev (otherwise it does not exist: 404)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends

from ..auth import AuthCtx
from ..deps import AppState, auth_ctx, get_state
from ..errors import not_found
from ..services.seed import seed_demo

router = APIRouter(prefix="/v1")


@router.post("/dev/seed")
async def dev_seed(
    reset: bool = False,
    body: dict[str, Any] | None = Body(default=None),
    auth: AuthCtx = Depends(auth_ctx),
    state: AppState = Depends(get_state),
) -> dict[str, Any]:
    if not state.settings.is_dev:
        raise not_found("route", "/v1/dev/seed")
    want_reset = reset or bool((body or {}).get("reset", False))
    return await seed_demo(state, auth.workspace_id, reset=want_reset)
