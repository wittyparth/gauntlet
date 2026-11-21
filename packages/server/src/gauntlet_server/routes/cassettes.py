"""Cassettes, replay and rejudge (P3-3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthCtx
from ..deps import AppState, auth_ctx, db_session, get_state
from ..errors import ApiError
from ..services.cassettes import (
    MAX_CASSETTE_BYTES,
    ArchiveOut,
    ImportOut,
    archive_cassette,
    episode_cassette,
    import_cassette_text,
)
from ..services.rejudge import RejudgeIn, RejudgeOut, rejudge
from ..services.replay import ReplayIn, ReplayOut, replay_episode

router = APIRouter(prefix="/v1")
NDJSON = "application/x-ndjson"


def _actor(auth: AuthCtx) -> str:
    return auth.key_name or auth.key_id


@router.get("/episodes/{episode_id}/cassette", response_class=Response)
async def get_cassette(
    episode_id: str,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> Response:
    """The episode's journal as JSON Lines: a manifest header, then events, then effects."""
    text = await episode_cassette(state, s, auth.workspace_id, episode_id)
    return Response(
        text,
        media_type=NDJSON,
        headers={"Content-Disposition": f'attachment; filename="{episode_id}.cassette.jsonl"'},
    )


@router.post("/episodes/{episode_id}/cassette/archive", response_model=ArchiveOut)
async def post_archive(
    episode_id: str,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> ArchiveOut:
    out = await archive_cassette(state, s, auth.workspace_id, episode_id, _actor(auth))
    await s.commit()
    return out


@router.post(
    "/cassettes",
    status_code=201,
    response_model=ImportOut,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {NDJSON: {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
async def post_cassette(
    request: Request,
    agent_version_id: str | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> ImportOut:
    """Import a cassette (NDJSON body, at most 20 MB) as a finished episode of a
    `purpose=import` run."""
    declared = int(request.headers.get("content-length") or 0)
    if declared > MAX_CASSETTE_BYTES:
        raise ApiError(413, "cassette_too_large", "cassettes are limited to 20 MB")
    body = await request.body()
    try:
        text = body.decode()
    except UnicodeDecodeError as exc:
        raise ApiError(422, "invalid_cassette", "the cassette is not UTF-8 text") from exc
    return await import_cassette_text(
        state, s, auth.workspace_id, text, agent_version_id, _actor(auth)
    )


@router.post("/episodes/{episode_id}/replay", response_model=ReplayOut)
async def post_replay(
    episode_id: str,
    body: ReplayIn,
    response: Response,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> ReplayOut:
    """`strict`: replay in-process and report whether it is identical (200). `agent_live`:
    create a replay run that follows the recording until the agent diverges (201)."""
    out = await replay_episode(state, s, auth.workspace_id, episode_id, body, _actor(auth))
    if body.mode == "agent_live":
        response.status_code = 201
    return out


@router.post("/episodes/{episode_id}/rejudge", response_model=RejudgeOut)
async def post_rejudge(
    episode_id: str,
    body: RejudgeIn | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> RejudgeOut:
    """Re-run the judges for `rubrics` (default: the scenario's) and replace those verdict
    rows. The journal is untouched; the episode outcome is recomputed."""
    return await rejudge(state, s, auth.workspace_id, episode_id, body or RejudgeIn(), _actor(auth))
