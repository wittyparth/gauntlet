"""OTLP/HTTP trace ingest (P5-1): `POST /v1/traces`."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthCtx
from ..db.models import Agent
from ..deps import AppState, auth_ctx, db_session, get_state
from ..errors import ApiError, not_found
from ..ingest.otlp import decode_request, encode_response, is_protobuf
from ..services.production import ingest_spans, record_rejected

router = APIRouter(prefix="/v1")


class PartialSuccess(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    rejected_spans: int = Field(default=0, alias="rejectedSpans")


class OtlpResponse(BaseModel):
    """The OTLP ExportTraceServiceResponse in its JSON mapping."""

    model_config = ConfigDict(populate_by_name=True)
    partial_success: PartialSuccess = Field(default_factory=PartialSuccess, alias="partialSuccess")


async def _rate_limited(state: AppState, key_id: str) -> bool:
    if state.redis is None:
        return False
    key = f"gauntlet:ingest:rl:{key_id}:{int(time.time())}"
    n = await state.redis.incr(key)
    await state.redis.expire(key, 5)
    return int(n) > state.settings.ingest_rate_per_s


@router.post("/traces", response_model=OtlpResponse, response_model_by_alias=True)
async def post_traces(
    request: Request,
    agent_id: str | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> Response | OtlpResponse:
    """OTLP/HTTP, protobuf or JSON. Needs the `ingest` scope (or `admin`). Everything is
    redacted before it is stored; re-sending spans changes nothing."""
    if not ({"ingest", "admin"} & set(auth.scopes)):
        raise ApiError(403, "forbidden", "this API key lacks the `ingest` scope")
    if await _rate_limited(state, auth.key_id):
        raise ApiError(429, "rate_limited", "too many trace exports")
    cfg = state.settings
    body = await request.body()
    if len(body) > cfg.ingest_max_bytes:
        await record_rejected(state, auth.workspace_id, 1)
        raise ApiError(
            413, "payload_too_large", f"exports are limited to {cfg.ingest_max_bytes} bytes"
        )
    spans = decode_request(body, request.headers.get("content-type"))
    if len(spans) > cfg.ingest_max_spans:
        await record_rejected(state, auth.workspace_id, len(spans))
        raise ApiError(
            413, "payload_too_large", f"exports are limited to {cfg.ingest_max_spans} spans"
        )
    if agent_id is not None:
        agent = await s.get(Agent, agent_id)
        if agent is None or agent.workspace_id != auth.workspace_id:
            raise not_found("agent", agent_id)
    await ingest_spans(s, state, auth.workspace_id, spans, nbytes=len(body), agent_id=agent_id)
    await s.commit()
    if is_protobuf(request.headers.get("content-type")):
        return Response(encode_response(0), media_type="application/x-protobuf")
    return OtlpResponse()
