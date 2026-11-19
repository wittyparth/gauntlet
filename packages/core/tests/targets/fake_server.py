"""A real Starlette app on an ephemeral port: OpenAI-compatible echo with scripted failures,
an HTTP JSON agent with and without conversation ids, and a wired agent that calls the facade."""

from __future__ import annotations

import asyncio
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


@dataclass
class FakeAgent:
    base_url: str = ""
    failures: list[int] = field(default_factory=list)  # statuses to return before succeeding
    requests: list[dict[str, Any]] = field(default_factory=list)
    conv_counter: int = 0
    reply_override: Any = None


def build_app(state: FakeAgent) -> Starlette:
    async def maybe_fail() -> JSONResponse | None:
        if state.failures:
            code = state.failures.pop(0)
            return JSONResponse(
                {"error": "scripted"}, status_code=code, headers={"retry-after": "0"}
            )
        return None

    async def chat(request: Request) -> JSONResponse:
        body = await request.json()
        state.requests.append({"path": "chat", "body": body, "headers": dict(request.headers)})
        if (fail := await maybe_fail()) is not None:
            return fail
        last = body["messages"][-1]["content"]
        content = state.reply_override if state.reply_override is not None else f"echo: {last}"
        return JSONResponse({"choices": [{"message": {"role": "assistant", "content": content}}]})

    async def agent(request: Request) -> JSONResponse:
        body = await request.json()
        state.requests.append({"path": "agent", "body": body, "headers": dict(request.headers)})
        if (fail := await maybe_fail()) is not None:
            return fail
        cid = body.get("conversation_id") or None
        if cid is None and request.query_params.get("ids") == "1":
            state.conv_counter += 1
            cid = f"conv_{state.conv_counter}"
        out: dict[str, Any] = {"data": {"answer": f"got: {body.get('text')}", "cid": cid}}
        return JSONResponse(out)

    async def not_json(request: Request) -> JSONResponse:
        from starlette.responses import PlainTextResponse

        return PlainTextResponse("hello")  # type: ignore[return-value]

    async def wired(request: Request) -> JSONResponse:
        body = await request.json()
        token = request.headers["x-gauntlet-episode"]
        base = request.headers["x-gauntlet-mock-base"]
        state.requests.append({"path": "wired", "headers": dict(request.headers)})
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{base}/mock/{token}/tools/lookup_order", json={"order_id": "ord_1"})
        status = r.json()["result"]["status"]
        content = f"order is {status} ({body['messages'][-1]['content']})"
        return JSONResponse({"choices": [{"message": {"content": content}}]})

    return Starlette(
        routes=[
            Route("/v1/chat/completions", chat, methods=["POST"]),
            Route("/agent", agent, methods=["POST"]),
            Route("/plain", not_json, methods=["POST"]),
            Route("/wired/chat/completions", wired, methods=["POST"]),
        ]
    )


@asynccontextmanager
async def serve(state: FakeAgent) -> AsyncIterator[FakeAgent]:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(
        uvicorn.Config(build_app(state), host="127.0.0.1", port=port, log_level="warning")
    )
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    state.base_url = f"http://127.0.0.1:{port}"
    try:
        yield state
    finally:
        server.should_exit = True
        await task
