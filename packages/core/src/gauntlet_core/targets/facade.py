"""The mock-world facade for wired targets. `LocalFacade` is the in-process Starlette app
used by the CLI and tests; the api-process version is P1-9 (CQ-B3)."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from gauntlet_core.engine import EpisodeCtx
from gauntlet_core.world import World

from .tokens import mint_token, verify_token

__all__ = ["Facade", "LocalFacade"]


class Facade(Protocol):
    @property
    def base_url(self) -> str: ...

    def attach(self, ctx: EpisodeCtx, world: World) -> str: ...

    def detach(self, token: str) -> None: ...


class LocalFacade:
    def __init__(self, host: str = "127.0.0.1", port: int = 0, *, secret: bytes) -> None:
        self._host, self._port, self._secret = host, port, secret
        self._eps: dict[str, tuple[EpisodeCtx, World, asyncio.Lock]] = {}
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task[None] | None = None
        self.app = Starlette(
            routes=[
                Route("/mock/tools", self._tools, methods=["GET"]),
                Route("/mock/tools/{tool}", self._call, methods=["POST"]),
                Route("/mock/{token}/tools", self._tools, methods=["GET"]),
                Route("/mock/{token}/tools/{tool}", self._call, methods=["POST"]),
                Route("/mock/{token}/mcp", self._mcp, methods=["GET", "POST", "DELETE"]),
            ]
        )

    # ------------------------------------------------------------- lifecycle

    @property
    def base_url(self) -> str:
        return f"http://{self._host}:{self._port}"

    async def start(self) -> None:
        config = uvicorn.Config(
            self.app, host=self._host, port=self._port, log_level="warning", lifespan="off"
        )
        self._server = uvicorn.Server(config)
        self._task = asyncio.create_task(self._server.serve())
        while not self._server.started:
            if self._task.done():
                self._task.result()
                raise RuntimeError("facade server exited during startup")
            await asyncio.sleep(0.01)
        sockets = self._server.servers[0].sockets
        self._port = sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is not None and self._task is not None:
            self._server.should_exit = True
            await self._task
        self._server = self._task = None

    # ---------------------------------------------------------------- attach

    def attach(self, ctx: EpisodeCtx, world: World) -> str:
        token = mint_token(ctx.episode_id, ctx.epoch, self._secret)
        self._eps[token] = (ctx, world, asyncio.Lock())
        return token

    def detach(self, token: str) -> None:
        self._eps.pop(token, None)

    # ---------------------------------------------------------------- routes

    def _lookup(self, request: Request) -> tuple[EpisodeCtx, World, asyncio.Lock] | None:
        token = request.path_params.get("token") or request.headers.get("x-gauntlet-episode")
        if not token:
            return None
        try:
            verify_token(token, self._secret)
        except ValueError:
            return None
        return self._eps.get(token)

    @staticmethod
    def _unauthorized() -> Response:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    async def _tools(self, request: Request) -> Response:
        found = self._lookup(request)
        if found is None:
            return self._unauthorized()
        return JSONResponse(found[1].tool_schemas(None))

    async def _call(self, request: Request) -> Response:
        found = self._lookup(request)
        if found is None:
            return self._unauthorized()
        ctx, world, lock = found
        tool = request.path_params["tool"]
        try:
            args: Any = await request.json()
        except ValueError:
            args = {}
        if not isinstance(args, dict):
            args = {}
        async with lock:  # tool effects take their ordinals one at a time
            res = await world.call_tool(ctx, tool, args, via="wired")
        return JSONResponse({"ok": res.ok, "result": res.result, "error": res.error})

    async def _mcp(self, request: Request) -> Response:
        return JSONResponse({"error": "not_implemented"}, status_code=501)
