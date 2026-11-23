from __future__ import annotations

import json
from typing import Any

ARGS = {"suite_id": "suite_1", "agent_version_id": "av_1"}


async def call(make_client: Any, **extra: Any) -> dict[str, Any]:
    async with make_client() as c:
        return json.loads((await c.call_tool("create_run", {**ARGS, **extra})).content[0].text)


async def test_refused_without_budget(make_client, api):
    assert "budget_usd" in (await call(make_client, confirm=True))["error"]
    assert api.run_posts == []


async def test_refused_without_confirm(make_client, api):
    assert "confirm" in (await call(make_client, budget_usd=0.5))["error"]
    assert api.run_posts == []


async def test_refused_over_cap_and_env_cap_respected(make_client, api, monkeypatch):
    assert "outside" in (await call(make_client, budget_usd=5, confirm=True))["error"]
    monkeypatch.setenv("GAUNTLET_MCP_MAX_BUDGET_USD", "10")
    assert (await call(make_client, budget_usd=5, confirm=True))["id"] == "run_1"
    assert api.run_posts[0]["budget_usd_micros"] == 5_000_000


async def test_accepted_within_cap(make_client, api):
    assert (await call(make_client, budget_usd=0.25, confirm=True))["status"] == "queued"
    assert api.run_posts[0]["budget_usd_micros"] == 250_000
