"""Runs, their episodes, the report and the SSE stream."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthCtx
from ..db.models import Episode, Run
from ..deps import AppState, auth_ctx, db_session, get_state
from ..errors import ApiError, not_found
from ..events import channel
from ..pagination import Page, paginate
from ..services.reports import episode_detail, episode_row_json, run_report
from ..services.runs import RunCreate, create_run, run_json, run_update_payload, set_run_status

router = APIRouter(prefix="/v1")
TERMINAL = ("done", "cancelled", "failed")


async def _run(s: AsyncSession, auth: AuthCtx, run_id: str) -> Run:
    run = await s.get(Run, run_id)
    if run is None or run.workspace_id != auth.workspace_id:
        raise not_found("run", run_id)
    return run


@router.post("/runs", status_code=201)
async def post_run(
    body: RunCreate,
    dry_run: bool = False,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> Any:
    out, status = await create_run(s, state, auth.workspace_id, body, dry_run=dry_run)
    if not dry_run:
        await s.commit()
    return JSONResponse(out, status_code=status)


@router.get("/runs")
async def list_runs(
    limit: int = 50,
    cursor: str | None = None,
    agent_version_id: str | None = None,
    suite_id: str | None = None,
    status: str | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    q = select(Run).where(Run.workspace_id == auth.workspace_id)
    if agent_version_id:
        q = q.where(Run.agent_version_id == agent_version_id)
    if suite_id:
        q = q.where(Run.suite_id == suite_id)
    if status:
        q = q.where(Run.status == status)
    page = await paginate(s, q, Run, Page(limit, cursor), lambda r: r)
    page["items"] = [await run_json(s, r) for r in page["items"]]
    return page


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    return await run_json(s, await _run(s, auth, run_id))


async def _transition(
    run_id: str, action: str, auth: AuthCtx, s: AsyncSession, state: AppState
) -> dict[str, Any]:
    run = await _run(s, auth, run_id)
    await set_run_status(s, run, action)
    await s.commit()
    await state.publisher.publish(run_id, "run_update", await run_update_payload(s, run_id))
    return await run_json(s, run)


@router.post("/runs/{run_id}/cancel")
async def cancel_run(
    run_id: str,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> dict[str, Any]:
    return await _transition(run_id, "cancel", auth, s, state)


@router.post("/runs/{run_id}/pause")
async def pause_run(
    run_id: str,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> dict[str, Any]:
    return await _transition(run_id, "pause", auth, s, state)


@router.post("/runs/{run_id}/resume")
async def resume_run(
    run_id: str,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> dict[str, Any]:
    return await _transition(run_id, "resume", auth, s, state)


@router.get("/runs/{run_id}/episodes")
async def list_run_episodes(
    run_id: str,
    limit: int = 50,
    cursor: str | None = None,
    status: str | None = None,
    outcome: str | None = None,
    scenario_id: str | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    await _run(s, auth, run_id)
    q = select(Episode).where(Episode.run_id == run_id)
    if status:
        q = q.where(Episode.status == status)
    if outcome:
        q = q.where(Episode.outcome == outcome)
    if scenario_id:
        q = q.where(Episode.scenario_id == scenario_id)
    return await paginate(s, q, Episode, Page(limit, cursor), episode_row_json)


@router.get("/runs/{run_id}/report")
async def get_report(
    run_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> Any:
    run = await _run(s, auth, run_id)
    report = await run_report(s, run)
    return JSONResponse(report.model_dump(mode="json"))


@router.get("/runs/{run_id}/compare", status_code=501)
async def compare(run_id: str, baseline: str, _: AuthCtx = Depends(auth_ctx)) -> None:
    raise ApiError(501, "not_implemented", "run comparison arrives in Phase 3")


@router.post("/episodes/{episode_id}/rejudge", status_code=501)
async def rejudge(episode_id: str, _: AuthCtx = Depends(auth_ctx)) -> None:
    raise ApiError(501, "not_implemented", "rejudge arrives in Phase 3")


@router.post("/agents/{agent_id}/generate-scenarios", status_code=501)
async def generate_scenarios(agent_id: str, _: AuthCtx = Depends(auth_ctx)) -> None:
    raise ApiError(501, "not_implemented", "scenario generation route is not wired yet")


@router.get("/episodes/{episode_id}")
async def get_episode(
    episode_id: str,
    events: str = "all",
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    return await episode_detail(s, auth.workspace_id, episode_id, events_mode=events)


# --------------------------------------------------------------------------------- SSE


def _sse(name: str, data: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


@router.get(
    "/runs/{run_id}/stream",
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def stream_run(
    run_id: str,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> StreamingResponse:
    await _run(s, auth, run_id)
    pubsub = state.redis.pubsub()
    await pubsub.subscribe(channel(run_id))  # subscribe first, then snapshot: no gap
    snapshot = await run_update_payload(s, run_id)
    await s.close()

    async def gen() -> AsyncIterator[str]:
        try:
            yield _sse("run_update", snapshot)
            if snapshot["status"] in TERMINAL:
                return
            while True:
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=state.sse_ping_s
                )
                if msg is None:
                    yield ": ping\n\n"
                    continue
                payload = json.loads(msg["data"])
                yield _sse(payload["event"], payload["data"])
                if payload["event"] == "run_update" and payload["data"]["status"] in TERMINAL:
                    return
        except asyncio.CancelledError:
            raise
        finally:
            await pubsub.unsubscribe(channel(run_id))
            await pubsub.aclose()

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
