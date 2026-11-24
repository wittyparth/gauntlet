"""The arena HTTP service: `/arena/v1`. A separate process from the platform API with its own
database URL setting; every route except `GET /levels` answers 503 while the arena is closed
(disabled by default, kill switch engaged, daily budget spent)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from gauntlet_core.llm import Gateway
from gauntlet_server.db import Sessionmaker, make_engine, make_sessionmaker
from pydantic import BaseModel, ConfigDict, Field

from .attempts import Arena, ArenaError
from .brain import ScriptedBrain
from .limits import ArenaClosed, RateLimited
from .settings import ArenaSettings

__all__ = ["create_app", "main"]

log = logging.getLogger("gauntlet.arena")
SWEEP_EVERY_S = 60


class HandleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    handle: str = Field(max_length=64)


class HandleOut(BaseModel):
    handle: str


class AttemptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    handle: str = Field(max_length=64)
    level: int


class MessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=4000)  # the real cap (ARENA_MAX_MESSAGE_CHARS) is enforced below


class AttemptOut(BaseModel):
    id: str
    handle: str
    level: int
    status: str
    turns: int
    max_turns: int
    expires_at: datetime


class TurnOut(BaseModel):
    reply: str
    status: str
    turns: int
    solved: bool
    closed_reason: str | None = None


class ChatMessage(BaseModel):
    role: str
    text: str


class AttemptDetail(AttemptOut):
    solved_at: datetime | None = None
    messages: list[ChatMessage]


class LevelOut(BaseModel):
    level: int
    title: str
    description: str
    defenses: list[str]
    classifier: str | None = None  # "fake" or "model" when the level runs the classifier


class LevelsOut(BaseModel):
    enabled: bool
    open: bool
    closed_reason: str | None = None
    levels: list[LevelOut]


class LeaderRow(BaseModel):
    rank: int
    handle: str
    level: int
    turns: int
    seconds: int


class LeaderboardOut(BaseModel):
    items: list[LeaderRow]


class OkOut(BaseModel):
    ok: bool = True


def _llm_brain() -> Gateway:
    from gauntlet_core.llm import GatewayConfig, LiteLLMGateway

    return LiteLLMGateway(GatewayConfig())


def create_app(
    settings: ArenaSettings | None = None,
    *,
    sm: Sessionmaker | None = None,
    redis: Any = None,
    brain: Gateway | None = None,
    sweeper: bool = True,
) -> FastAPI:
    cfg = settings or ArenaSettings.from_env()
    holder: dict[str, Any] = {}

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = None
        maker = sm
        if maker is None:
            engine = make_engine(cfg.database_url)
            maker = make_sessionmaker(engine)
        r = redis
        if r is None:
            import redis.asyncio as aioredis

            r = aioredis.from_url(cfg.redis_url)
        b = brain or (ScriptedBrain() if cfg.brain == "scripted" else _llm_brain())
        arena = Arena(cfg, maker, r, b)
        holder["arena"] = arena
        task = asyncio.create_task(_sweep_loop(arena)) if sweeper else None
        try:
            yield
        finally:
            if task:
                task.cancel()
            await arena.shutdown()
            if engine is not None:
                await engine.dispose()

    app = FastAPI(title="Gauntlet arena", version="1", lifespan=lifespan)

    def arena() -> Arena:
        return holder["arena"]  # type: ignore[no-any-return]

    @app.exception_handler(ArenaError)
    async def _arena_error(request: Request, exc: ArenaError) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status
        )

    @app.exception_handler(ArenaClosed)
    async def _closed(request: Request, exc: ArenaClosed) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": "arena_closed", "message": f"The arena is closed ({exc.reason})."}},
            status_code=503,
        )

    @app.exception_handler(RateLimited)
    async def _limited(request: Request, exc: RateLimited) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": "rate_limited", "message": "Slow down a little."}},
            status_code=429,
            headers={"Retry-After": str(exc.retry_after_s)},
        )

    def client_ip(request: Request) -> str:
        if cfg.trust_proxy:
            fwd = request.headers.get("x-forwarded-for", "")
            if fwd:
                return fwd.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def throttle(request: Request) -> None:
        await arena().limiter.ip(client_ip(request))

    @app.get("/arena/v1/levels", response_model=LevelsOut)
    async def levels() -> LevelsOut:
        a = arena()
        reason = await a.closed()
        return LevelsOut(
            enabled=cfg.enabled, open=reason is None, closed_reason=reason,
            levels=[LevelOut(**d) for d in a.level_docs()],
        )  # fmt: skip

    @app.post("/arena/v1/handles", response_model=HandleOut, status_code=201)
    async def handles(body: HandleIn, request: Request) -> HandleOut:
        await throttle(request)
        return HandleOut(handle=await arena().create_handle(body.handle))

    @app.post("/arena/v1/attempts", response_model=AttemptOut, status_code=201)
    async def start(body: AttemptIn, request: Request) -> AttemptOut:
        await throttle(request)
        v = await arena().start_attempt(body.handle, body.level)
        return AttemptOut(
            id=v.id, handle=v.handle, level=v.level, status=v.status, turns=v.turns,
            max_turns=v.max_turns, expires_at=v.expires_at,
        )  # fmt: skip

    @app.post("/arena/v1/attempts/{attempt_id}/messages", response_model=TurnOut)
    async def message(attempt_id: str, body: MessageIn, request: Request) -> TurnOut:
        await throttle(request)
        r = await arena().message(attempt_id, body.text)
        return TurnOut(
            reply=r.reply, status=r.status, turns=r.turns, solved=r.solved,
            closed_reason=r.closed_reason,
        )  # fmt: skip

    @app.get("/arena/v1/attempts/{attempt_id}", response_model=AttemptDetail)
    async def attempt(attempt_id: str, request: Request) -> AttemptDetail:
        await throttle(request)
        return AttemptDetail.model_validate(await arena().get(attempt_id))

    @app.get("/arena/v1/leaderboard", response_model=LeaderboardOut)
    async def leaderboard(level: int | None = Query(default=None, ge=1, le=5)) -> LeaderboardOut:
        rows = await arena().leaderboard(level)
        return LeaderboardOut(items=[LeaderRow(**r) for r in rows])

    @app.post("/arena/v1/attempts/{attempt_id}/report", response_model=OkOut)
    async def report(attempt_id: str, request: Request) -> OkOut:
        await throttle(request)
        await arena().report(attempt_id)
        return OkOut()

    return app


async def _sweep_loop(arena: Arena) -> None:
    while True:
        await asyncio.sleep(SWEEP_EVERY_S)
        try:
            await arena.sweep()
        except Exception:
            log.warning("arena: sweep failed", exc_info=True)


def main() -> None:
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8100)


if __name__ == "__main__":
    main()
