from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import mcp_types as types
from gauntlet_core.gateway import Guard, JsonlSink, MemorySink
from gauntlet_core.gateway.mcp import McpGateway, McpGatewayConfig, PinStore
from gauntlet_core.schema import Policy
from mcp import Client

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "mcp" / "env_server.py"


async def test_stdio_upstream_gets_only_the_configured_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("GW_SECRET", "s3cret-token-value")
    monkeypatch.setenv("AGENT_CLIENT_CREDENTIAL", "agent-owned-credential")  # must not leak
    cfg = McpGatewayConfig.model_validate(
        {
            "on_unpinned": "warn",
            "servers": [
                {
                    "name": "envs",
                    "transport": "stdio",
                    "command": [sys.executable, str(FIXTURE)],
                    "env": {"ROOT_DIR": "/srv/data", "TOKEN": "${GW_SECRET}"},
                }
            ],
        }
    )
    sink = MemorySink()
    log_path = tmp_path / "decisions.jsonl"
    jsonl = JsonlSink(log_path)

    class Both:
        async def write(self, record):
            await sink.write(record)
            await jsonl.write(record)

    guard = Guard(Policy(id="p", rules=[]), sink=Both())
    gw = McpGateway(cfg, guard, pins=PinStore())
    async with gw, Client(gw.server) as agent:
        res = await agent.call_tool("envs__env_report", {})
    body = json.loads("".join(c.text for c in res.content if isinstance(c, types.TextContent)))
    keys = set(body["keys"])
    assert {"ROOT_DIR", "TOKEN", "PATH"} <= keys
    assert "AGENT_CLIENT_CREDENTIAL" not in keys and "GW_SECRET" not in keys
    assert body["token_sha"] == hashlib.sha256(b"s3cret-token-value").hexdigest()
    # the value that was interpolated never reaches decision records or their log file
    dumped = log_path.read_text() + "".join(r.model_dump_json() for r in sink.records)
    assert "s3cret-token-value" not in dumped and "agent-owned-credential" not in dumped
    assert "${GW_SECRET}" in repr(cfg)
