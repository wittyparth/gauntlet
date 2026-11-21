"""The DVA HTTP app: an OpenAI-compatible `/v1/chat/completions` in front of the brains.

INTENTIONALLY VULNERABLE. Binds to 127.0.0.1 by default. Never expose it publicly."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import brain_llm, brain_scripted
from .config import Settings, load_settings
from .flaws import FLAWS, active_flaws
from .tools_client import ToolsClient

__all__ = ["create_app", "main"]

log = logging.getLogger("dva")


Scripted = Callable[[list[dict[str, Any]], set[str], Callable[..., Any]], Awaitable[str]]


def create_app(
    flaws: Callable[[], set[str]] | None = None,
    settings: Settings | None = None,
    *,
    scripted: Scripted | None = None,
    system_prompt: Callable[[set[str]], str] | None = None,
) -> FastAPI:
    cfg = settings or load_settings()
    flaws_now = flaws or active_flaws
    app = FastAPI(title="Damn Vulnerable Agent", docs_url=None, redoc_url=None)

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"ok": True, "brain": cfg.brain, "world": cfg.world, "flaws": sorted(flaws_now())}

    @app.post("/v1/chat/completions")
    async def chat(request: Request) -> JSONResponse:
        token = request.headers.get("x-gauntlet-episode")
        if not token:
            return JSONResponse({"error": "X-Gauntlet-Episode header required"}, status_code=400)
        try:
            body = await request.json()
            messages = list(body["messages"])
        except (ValueError, KeyError, TypeError):
            return JSONResponse({"error": "body needs a messages list"}, status_code=400)
        base = request.headers.get("x-gauntlet-mock-base") or cfg.mock_base
        active = flaws_now()
        async with httpx.AsyncClient(timeout=30) as client:
            tools = ToolsClient(client, base, token)
            if cfg.brain == "scripted":
                reply = await (scripted or brain_scripted.respond)(messages, active, tools.call)
            else:
                reply = await brain_llm.respond(
                    messages,
                    active,
                    tools.call,
                    await tools.list_tools(),
                    model=cfg.model,
                    system=system_prompt(active) if system_prompt else None,
                )
        return JSONResponse(
            {
                "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": body.get("model", cfg.model),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": reply},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }
        )

    return app


def main() -> None:
    cfg = load_settings()
    logging.basicConfig(level=logging.INFO)
    active = active_flaws()
    log.warning(
        "DVA is INTENTIONALLY VULNERABLE (brain=%s). Active flaws: %s",
        cfg.brain,
        ", ".join(f"{i} {FLAWS[i].title}" for i in sorted(active)) or "none",
    )
    uvicorn.run(create_app(settings=cfg), host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()
