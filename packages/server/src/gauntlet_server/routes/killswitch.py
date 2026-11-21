"""Kill switch routes."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthCtx
from ..deps import AppState, auth_ctx, db_session, get_state
from ..services import killswitch as ks

router = APIRouter(prefix="/v1")


class KillEngage(BaseModel):
    scope: Literal["workspace", "run"]
    run_id: str | None = None
    reason: str


class KillRow(BaseModel):
    id: str
    scope: str
    run_id: str | None
    reason: str
    engaged_by: str
    engaged_at: str


class KillState(BaseModel):
    engaged: bool
    switches: list[KillRow]


async def _state(s: AsyncSession, ws: str) -> dict[str, Any]:
    rows = await ks.active_rows(s, ws)
    return {
        "engaged": bool(rows),
        "switches": [
            {
                "id": r.id, "scope": r.scope, "run_id": r.run_id, "reason": r.reason,
                "engaged_by": r.engaged_by, "engaged_at": r.engaged_at.isoformat(),
            }
            for r in rows
        ],
    }  # fmt: skip


@router.get("/killswitch", response_model=KillState)
async def get_killswitch(
    auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    return await _state(s, auth.workspace_id)


@router.post("/killswitch", status_code=201, response_model=KillState)
async def engage(
    body: KillEngage,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> dict[str, Any]:
    """Engaging also cancels queued attack episodes and attack runs at once; leased episodes
    are cancelled by their workers within the poll interval."""
    actor = auth.key_name or auth.key_id
    await ks.engage(
        s, state.redis, auth.workspace_id, actor,
        scope=body.scope, run_id=body.run_id, reason=body.reason,
    )  # fmt: skip
    await ks.cancel_attack_runs(s, auth.workspace_id, body.run_id if body.scope == "run" else None)
    await s.commit()
    return await _state(s, auth.workspace_id)


@router.delete("/killswitch", response_model=KillState)
async def release(
    scope: Literal["workspace", "run"] = "workspace",
    run_id: str | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> dict[str, Any]:
    await ks.release(s, state.redis, auth.workspace_id, auth.key_name or auth.key_id,
                     scope=scope, run_id=run_id)  # fmt: skip
    await s.commit()
    return await _state(s, auth.workspace_id)
