from __future__ import annotations

import json
from typing import Any

EXPECTED = [
    "compare_runs",
    "create_run",
    "generate_scenarios",
    "get_episode",
    "get_finding",
    "get_run_report",
    "list_agents",
    "list_findings",
    "list_policies",
    "list_runs",
]


def text(res: Any) -> str:
    return res.content[0].text


async def test_tool_list_has_no_destructive_tools(make_client):
    async with make_client() as c:
        names = sorted(t.name for t in (await c.list_tools()).tools)
    assert names == EXPECTED


async def test_read_flow_and_workspace_follows_the_key(make_client, api):
    async with make_client("gk_a") as c:
        assert json.loads(text(await c.call_tool("list_agents", {})))["items"][0]["id"] == "agt_wsA"
    async with make_client("gk_b") as c:
        assert json.loads(text(await c.call_tool("list_agents", {})))["items"][0]["id"] == "agt_wsB"
    assert all(r.method == "GET" for r in api.requests)


async def test_api_errors_come_back_as_error_results(make_client):
    async with make_client("gk_bad") as c:
        out = json.loads(text(await c.call_tool("list_agents", {})))
    assert "401" in out["error"]
