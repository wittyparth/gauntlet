"""In-process fake upstream MCP servers and a gateway builder for the proxy tests."""

from __future__ import annotations

from typing import Any

import mcp_types as types
from gauntlet_core.gateway import Guard, MemorySink
from gauntlet_core.gateway.mcp import McpGateway, McpGatewayConfig, PinStore
from gauntlet_core.schema import Policy
from mcp.server import Server


class FakeUpstream:
    """A lowlevel MCP server whose tools can be changed after it started."""

    def __init__(self, name: str, tools: dict[str, dict[str, Any]]) -> None:
        self.name = name
        self.tools = tools  # name -> {description, annotations?, inputSchema?}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.server: Server[Any] = Server(name, on_list_tools=self._list, on_call_tool=self._call)

    async def _list(self, ctx: Any, params: Any) -> types.ListToolsResult:
        return types.ListToolsResult(tools=[self.tool(n) for n in self.tools])

    def tool(self, name: str) -> types.Tool:
        spec = self.tools[name]
        return types.Tool.model_validate(
            {
                "name": name,
                "description": spec.get("description"),
                "inputSchema": spec.get("inputSchema", {"type": "object", "properties": {}}),
                "annotations": spec.get("annotations"),
            }
        )

    async def _call(self, ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
        self.calls.append((params.name, dict(params.arguments or {})))
        return types.CallToolResult(
            content=[types.TextContent(text=f"{self.name}:{params.name}:ok")]
        )


def files_upstream() -> FakeUpstream:
    return FakeUpstream(
        "files",
        {
            "read_file": {
                "description": "Read a file.",
                "annotations": {"readOnlyHint": True},
                "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}},
            },
            "write_file": {"description": "Write a file."},
            "delete_file": {
                "description": "Delete a file.",
                "annotations": {"destructiveHint": True},
            },
        },
    )


def crm_upstream() -> FakeUpstream:
    return FakeUpstream(
        "crm",
        {"read_file": {"description": "Read a CRM note.", "annotations": {"readOnlyHint": True}}},
    )


def config(
    *servers: str, per_server: dict[str, dict[str, Any]] | None = None, **extra: Any
) -> McpGatewayConfig:
    per = per_server or {}
    doc: dict[str, Any] = {
        "servers": [
            {"name": n, "transport": "http", "url": f"http://{n}.test/mcp", **per.get(n, {})}
            for n in servers
        ],
        **extra,
    }
    return McpGatewayConfig.model_validate(doc)


def pinned(*upstreams: FakeUpstream) -> PinStore:
    store = PinStore()
    for up in upstreams:
        tools = [
            t.model_dump(mode="json", by_alias=True, exclude_none=True)
            for t in (up.tool(n) for n in up.tools)
        ]
        store.approve(up.name, tools)
    return store


def policy(*rules: dict[str, Any], mode: str = "enforce") -> Policy:
    return Policy.model_validate({"id": "pol_mcp", "mode": mode, "rules": list(rules)})


def gateway(
    cfg: McpGatewayConfig,
    upstreams: list[FakeUpstream],
    *,
    pins: PinStore | None = None,
    pol: Policy | None = None,
    **guard_kw: Any,
) -> tuple[McpGateway, MemorySink]:
    sink = MemorySink()
    guard = Guard(pol or policy(), sink=sink, **guard_kw)
    gw = McpGateway(
        cfg,
        guard,
        pins=pins if pins is not None else pinned(*upstreams),
        targets={u.name: u.server for u in upstreams},
    )
    return gw, sink
