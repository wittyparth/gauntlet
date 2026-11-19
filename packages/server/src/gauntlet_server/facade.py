"""The api-process mock facade for wired targets (hard-cores 2.6, 1.7a, CQ-B3).

`/mock/{episode_token}/tools[/{tool}]`: verify the token (HMAC of episode id and epoch), take a
per-episode lock, rebuild the world by folding the journal, run the tool through the same
`World.call_tool` / `EpisodeCtx.effect` path with the token's epoch, and append. The owning
worker is blocked awaiting the agent's reply and appends nothing meanwhile; when the reply
arrives it reloads the journal tail (`nested=True` effects) and replays our events into its
world through the replay hook.

Serialisation: concurrent tool calls of one episode queue on a Postgres advisory lock held in
a transaction for the whole call, so ordinal keys and `seq` are assigned one call at a time.
(The journal store takes the episode row lock itself on append; holding that row lock here
too would deadlock against it, hence the advisory lock.)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from gauntlet_core.engine import EpisodeCtx, SeqConflict, StaleLease
from gauntlet_core.runner import make_llm_sim
from gauntlet_core.targets.tokens import mint_token, verify_token
from gauntlet_core.world import World, build_world
from sqlalchemy import text

from .deps import AppState
from .jobs import load_episode_job
from .stores import PgBudgetLedger, PgJournalStore

__all__ = ["RemoteFacade", "router"]

log = logging.getLogger("gauntlet.facade")
router = APIRouter()


class RemoteFacade:
    """`Facade` for the worker: tokens are minted for the api's `/mock` routes."""

    def __init__(self, base_url: str, secret: bytes) -> None:
        self._base_url, self._secret = base_url.rstrip("/"), secret

    @property
    def base_url(self) -> str:
        return self._base_url

    def attach(self, ctx: EpisodeCtx, world: World) -> str:
        return mint_token(ctx.episode_id, ctx.epoch, self._secret)

    def detach(self, token: str) -> None:
        return None


def _err(status: int, code: str, message: str = "") -> JSONResponse:
    return JSONResponse({"error": code, "message": message}, status_code=status)


def _token(request: Request) -> str | None:
    return request.path_params.get("token") or request.headers.get("x-gauntlet-episode")


async def _verified(request: Request) -> tuple[AppState, str, int] | JSONResponse:
    state: AppState = request.app.state.gauntlet
    token = _token(request)
    if not token:
        return _err(401, "unauthorized")
    try:
        episode_id, epoch = verify_token(token, state.settings.mock_secret())
    except ValueError:
        return _err(401, "unauthorized")
    return state, episode_id, epoch


async def _open(state: AppState, episode_id: str, epoch: int):
    """(job, world, ctx) for the episode, positioned at the end of its journal."""
    async with state.sm() as s:
        job = await load_episode_job(s, episode_id)
    store = PgJournalStore(state.sm)
    ctx = await EpisodeCtx.open(
        store,
        episode_id,
        epoch=epoch,
        run_id=job.run_id,
        rng_seed=job.rng_seed,
        budget=PgBudgetLedger(state.sm),
        secrets=tuple(job.secrets.values()),
    )
    live = await store.load(episode_id)
    if live.epoch != epoch:
        raise StaleLease(f"{episode_id}: token epoch {epoch} is not current ({live.epoch})")
    built = build_world(job.world, job.scenario.world_overrides, job.rng_seed)
    world = World(built, llm_sim=make_llm_sim(state.gateway))
    world.bind(ctx)
    ctx.seek_end()
    return job, world, ctx


@router.get("/mock/tools", include_in_schema=False)
@router.get("/mock/{token}/tools", include_in_schema=False)
async def list_tools(request: Request) -> Any:
    v = await _verified(request)
    if isinstance(v, JSONResponse):
        return v
    state, episode_id, epoch = v
    try:
        job, world, _ = await _open(state, episode_id, epoch)
    except StaleLease:
        return _err(409, "stale_episode")
    cfg = job.agent_version.target
    subset = getattr(cfg, "tools", None)
    return world.tool_schemas(subset)


@router.post("/mock/tools/{tool}", include_in_schema=False)
@router.post("/mock/{token}/tools/{tool}", include_in_schema=False)
async def call_tool(request: Request, tool: str) -> Any:
    v = await _verified(request)
    if isinstance(v, JSONResponse):
        return v
    state, episode_id, epoch = v
    try:
        args: Any = await request.json()
    except ValueError:
        args = {}
    if not isinstance(args, dict):
        args = {}
    try:
        async with state.sm() as s, s.begin():
            await s.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:id, 0))"), {"id": episode_id}
            )
            _, world, ctx = await _open(state, episode_id, epoch)
            res = await world.call_tool(ctx, tool, args, via="wired")
            await ctx.flush()  # the trailing tool_result events
    except (StaleLease, SeqConflict):
        return _err(409, "stale_episode")
    return {"ok": res.ok, "result": res.result, "error": res.error}


@router.api_route("/mock/{token}/mcp", methods=["GET", "POST", "DELETE"], include_in_schema=False)
async def mcp(request: Request) -> Any:
    return _err(501, "not_implemented", "MCP facade arrives after Phase 1")
