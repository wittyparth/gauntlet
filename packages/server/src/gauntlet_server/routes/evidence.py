"""Evidence packs (P5-7): queue a build, list, inspect, download the zip."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthCtx
from ..deps import AppState, auth_ctx, db_session, get_state
from ..services.evidence import (
    EvidenceIn,
    EvidencePackOut,
    create_pack,
    download_pack,
    get_pack,
    list_packs,
)

router = APIRouter(prefix="/v1/evidence-packs")


def _actor(a: AuthCtx) -> str:
    return a.key_name or a.key_id


@router.post("", status_code=202, response_model=EvidencePackOut)
async def post_pack(
    body: EvidenceIn,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> EvidencePackOut:
    """Queues the build job (no model calls). Poll the pack until `done`."""
    return await create_pack(state, s, auth.workspace_id, body, _actor(auth))


@router.get("", response_model=list[EvidencePackOut])
async def get_packs(
    auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> list[EvidencePackOut]:
    return await list_packs(s, auth.workspace_id)


@router.get("/{pack_id}", response_model=EvidencePackOut)
async def get_one(
    pack_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> EvidencePackOut:
    return await get_pack(s, auth.workspace_id, pack_id)


@router.get("/{pack_id}/download")
async def download(
    pack_id: str,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> Response:
    data = await download_pack(state, s, auth.workspace_id, pack_id, _actor(auth))
    return Response(
        data, media_type="application/zip",
        headers={"content-disposition": f'attachment; filename="{pack_id}.zip"'},
    )  # fmt: skip
