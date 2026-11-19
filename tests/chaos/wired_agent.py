"""A deterministic OpenAI-compatible "wired" agent for the chaos test (run as a subprocess).

It looks the order up and, when the customer asks for a refund, issues exactly one refund
through the api mock facade (`X-Gauntlet-Mock-Base` + `X-Gauntlet-Episode`), sleeping between
the steps so a SIGKILL has a wide window to land mid-turn. A facade error (a stale token after
a worker died) is reported in the reply, not retried: the platform owns recovery.

`python tests/chaos/wired_agent.py <port> <delay_s>`
"""

from __future__ import annotations

import asyncio
import re
import sys

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

DELAY = 0.3


async def chat(request: Request) -> JSONResponse:
    body = await request.json()
    token = request.headers.get("x-gauntlet-episode", "")
    base = request.headers.get("x-gauntlet-mock-base", "")
    user = [m["content"] for m in body["messages"] if m["role"] == "user"][-1]
    m = re.search(r"ord_\d+", user)
    order_id = m.group(0) if m else "ord_1004"

    async def tool(name: str, args: dict) -> dict:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{base}/mock/{token}/tools/{name}", json=args)
        return r.json() if r.status_code == 200 else {"ok": False, "error": r.text}

    await asyncio.sleep(DELAY)
    order = await tool("lookup_order", {"order_id": order_id})
    result = order.get("result") or {}
    await asyncio.sleep(DELAY)
    if "refund" in user.lower() and order.get("ok"):
        done = await tool(
            "issue_refund",
            {
                "order_id": order_id,
                "amount_cents": int(result.get("total_cents", 0)),
                "reason": "customer request",
            },
        )
        await asyncio.sleep(DELAY)
        text = f"Refund for {order_id}: {'issued' if done.get('ok') else 'failed'}."
    else:
        text = f"Order {order_id} is {result.get('status', 'unknown')}."
    return JSONResponse({"choices": [{"message": {"role": "assistant", "content": text}}]})


app = Starlette(routes=[Route("/v1/chat/completions", chat, methods=["POST"])])

if __name__ == "__main__":
    DELAY = float(sys.argv[2])
    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
