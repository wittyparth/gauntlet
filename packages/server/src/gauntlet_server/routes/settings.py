"""Attack scope settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthCtx
from ..deps import auth_ctx, db_session
from ..services.audit import audit
from ..services.scope import AttackScope, load_doc, store_doc

router = APIRouter(prefix="/v1")


@router.get("/settings/attack-scope", response_model=AttackScope)
async def get_scope(
    auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> AttackScope:
    return (await load_doc(s, auth.workspace_id)).attack_scope


@router.put("/settings/attack-scope", response_model=AttackScope)
async def put_scope(
    body: AttackScope, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> AttackScope:
    doc = await load_doc(s, auth.workspace_id)
    await store_doc(s, auth.workspace_id, doc.model_copy(update={"attack_scope": body}))
    await audit(
        s, auth.workspace_id, auth.key_name or auth.key_id, "scope.updated", "settings",
        "attack-scope", {"keys": sorted(body.model_dump())},
    )  # fmt: skip
    await s.commit()
    return body
