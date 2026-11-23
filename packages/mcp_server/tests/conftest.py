from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from gauntlet_mcp.client import Client
from gauntlet_mcp.server import build_server
from mcp import Client as McpClient


class FakeApi:
    """A fake platform API: two workspaces told apart by the bearer key."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.run_posts: list[dict[str, Any]] = []

    def handle(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        key = req.headers["authorization"].removeprefix("Bearer ")
        ws = {"gk_a": "wsA", "gk_b": "wsB"}.get(key)
        if ws is None:
            return httpx.Response(401, json={"error": {"message": "bad key"}})
        path = req.url.path
        if req.method == "POST" and path == "/v1/runs":
            self.run_posts.append(json.loads(req.content))
            return httpx.Response(201, json={"id": "run_1", "status": "queued"})
        if path == "/v1/agents":
            return httpx.Response(200, json={"items": [{"id": f"agt_{ws}", "name": ws}]})
        if path == "/v1/runs/run_big/report":
            return httpx.Response(200, json={"blob": "x" * 50_000})
        if path == "/v1/runs/run_1/report":
            return httpx.Response(
                200, json={"id": "run_1", "api_key": "gk_leak", "nested": {"secret_token": "s"}}
            )
        return httpx.Response(404, json={"error": {"message": "not found"}})


@pytest.fixture
def api() -> FakeApi:
    return FakeApi()


@pytest.fixture
def make_client(api: FakeApi) -> Callable[[str], McpClient]:
    def make(key: str = "gk_a") -> McpClient:
        client = Client("http://api.test", key, httpx.MockTransport(api.handle))
        return McpClient(build_server(client))

    return make
