"""The MCP gateway proxy (P4-3): one MCP server for the agent client, in front of the
configured upstream servers.

Needs the `mcp` extra (SDK 2.x: `mcp.Client`, lowlevel `mcp.server.Server`). Tools only:
progress notifications, resources and prompts are not proxied (and so not policy-checked).
Pin and scan decisions apply in every mode: they protect the integrity of the tool surface and
are configured in `gateway.yaml`, unlike policy rules, which `shadow` mode never enforces.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping
from contextlib import AsyncExitStack
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any, Literal, cast

import mcp_types as types
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.client.streamable_http import (
    create_mcp_http_client,  # pyright: ignore[reportPrivateImportUsage]
    streamable_http_client,
)
from mcp.server import NotificationOptions, Server, ServerRequestContext
from mcp.shared.exceptions import MCPError

from gauntlet_core.gateway.decision import DecisionRecord
from gauntlet_core.gateway.guard import Guard
from gauntlet_core.gateway.session import Session
from gauntlet_core.ids import new_id
from gauntlet_core.schema import Policy

from .config import RISK_ORDER, McpGatewayConfig, ServerConfig
from .namespace import UnknownTool, describe, expose_name, split_exposed
from .pins import PinStore, tool_pin_hash
from .scan_hook import ScanHook

__all__ = ["McpGateway", "default_risk", "fetch_tools"]

log = logging.getLogger("gauntlet.gateway.mcp")


@dataclass(frozen=True)
class Exposed:
    server: str
    original: str
    tool: dict[str, Any]  # what the agent sees (namespaced)
    risk: str
    hash: str


def default_risk(tool: Mapping[str, Any]) -> str:
    """From MCP annotation hints; a tool with neither hint is treated as `write` (CQ-G6)."""
    ann = tool.get("annotations") or {}
    if ann.get("destructiveHint") is True:
        return "destructive"
    if ann.get("readOnlyHint") is True:
        return "read"
    return "write"


class McpGateway:
    def __init__(
        self,
        config: McpGatewayConfig,
        guard: Guard | None = None,
        *,
        pins: PinStore | None = None,
        targets: Mapping[str, Any] | None = None,
    ) -> None:
        """`targets` replaces how a named upstream is reached (an in-process `Server` in
        tests); by default servers are launched or contacted as configured."""
        self.config = config
        if guard is None:
            guard = (
                Guard(config.policy, mode=config.mode)
                if config.policy
                else Guard(Policy(id="mcp-gateway", rules=[]), mode=config.mode or "enforce")
            )
        self.guard = guard
        self.pins = pins if pins is not None else PinStore.load(config.pins)
        self._targets = dict(targets or {})
        self.scan = ScanHook(config.scan.block_at)
        self.server: Server[Any] = Server(
            "gauntlet-mcp-gateway",
            on_list_tools=self._on_list_tools,
            on_call_tool=self._on_call_tool,
        )
        self._stack: AsyncExitStack | None = None
        self._clients: dict[str, Client] = {}
        self._exposed: dict[str, Exposed] = {}
        self._lock = asyncio.Lock()
        self._reported: set[tuple[str, str, str]] = set()
        self._client_sessions: dict[str, tuple[Any, Session]] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self.notifications_sent = 0

    # -- lifecycle --------------------------------------------------------------------------

    async def __aenter__(self) -> McpGateway:
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def start(self) -> None:
        self._stack = AsyncExitStack()
        try:
            for srv in self.config.servers:
                target = self._targets.get(srv.name) or self._target(srv)
                client = Client(target, message_handler=self._upstream_handler(srv.name))
                self._clients[srv.name] = await self._stack.enter_async_context(client)
            await self.refresh(notify=False)
        except BaseException:
            await self.aclose()
            raise

    async def aclose(self) -> None:
        for t in list(self._tasks):
            t.cancel()
        if self._stack is not None:
            stack, self._stack = self._stack, None
            await stack.aclose()
        self._clients.clear()

    @staticmethod
    def _target(srv: ServerConfig) -> Any:
        if srv.transport == "stdio":
            assert srv.command
            return StdioServerParameters(
                command=srv.command[0], args=srv.command[1:], env=srv.resolved_env()
            )
        assert srv.url
        headers = srv.resolved_headers()
        http = create_mcp_http_client(headers=headers) if headers else None
        return streamable_http_client(srv.url, http_client=http)

    # -- the exposed tool surface -----------------------------------------------------------

    def _upstream_handler(self, name: str) -> Any:
        async def handle(message: Any) -> None:
            if isinstance(message, types.ToolListChangedNotification):
                task = asyncio.create_task(self.refresh(notify=True))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

        return handle

    async def _list_upstream(self, name: str) -> list[dict[str, Any]] | None:
        client = self._clients.get(name)
        if client is None:
            return None
        out: list[dict[str, Any]] = []
        try:
            cursor: str | None = None
            while True:
                page = await client.list_tools(cursor=cursor)
                out += [
                    t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in page.tools
                ]
                cursor = page.next_cursor
                if not cursor:
                    return out
        except Exception as e:  # fail closed: an unreachable upstream exposes nothing
            log.warning("mcp gateway: cannot list tools of %s (%s)", name, type(e).__name__)
            return None

    async def refresh(self, *, notify: bool) -> None:
        """Re-list every upstream, recompute pins, scans and filters, and (with `notify`) tell
        the connected clients when the exposed set changed."""
        async with self._lock:
            new: dict[str, Exposed] = {}
            for srv in self.config.servers:
                tools = await self._list_upstream(srv.name)
                if tools is not None:
                    new.update(await self._expose(srv, tools))
            before = {k: v.hash for k, v in self._exposed.items()}
            self._exposed = new
            changed = before != {k: v.hash for k, v in new.items()}
        if notify and changed:
            await self._notify()

    async def _expose(self, srv: ServerConfig, tools: list[dict[str, Any]]) -> dict[str, Exposed]:
        cfg = self.config
        hidden: dict[str, str] = {}  # original name -> why (record rule id)
        report = self.pins.check(srv.name, tools)
        for st in report.tools:
            exposed_name = expose_name(srv.name, st.tool)
            if st.status == "changed":
                block = cfg.on_pin_mismatch == "block"
                await self._report(
                    "mcp.pin_mismatch", "critical", exposed_name, block, st.hash or "",
                    "tool definition changed since it was approved",
                )  # fmt: skip
                if block:
                    hidden[st.tool] = "mcp.pin_mismatch"
            elif st.status == "new":
                block = cfg.on_unpinned == "block"
                await self._report(
                    "mcp.unpinned", "medium", exposed_name, block, st.hash or "",
                    "tool was never approved",
                )  # fmt: skip
                if block:
                    hidden[st.tool] = "mcp.unpinned"
            elif st.status == "removed":
                await self._report(
                    "mcp.pin_removed", "low", exposed_name, False, st.pinned_hash or "",
                    "an approved tool is no longer offered",
                )  # fmt: skip
        for name, findings in self.scan.blocked(tools).items():
            rules = ",".join(sorted({f.rule_id for f in findings}))
            worst = max(
                findings, key=lambda f: ("low", "medium", "high", "critical").index(f.severity)
            )
            await self._report(
                "mcp.scan_blocked", worst.severity, expose_name(srv.name, name), True,
                tool_pin_hash(next(t for t in tools if t["name"] == name)),
                f"description scan: {rules}",
            )  # fmt: skip
            hidden.setdefault(name, "mcp.scan_blocked")
        out: dict[str, Exposed] = {}
        for tool in tools:
            name = str(tool["name"])
            if name in hidden:
                continue
            if srv.allow_tools and not any(fnmatchcase(name, p) for p in srv.allow_tools):
                continue
            if any(fnmatchcase(name, p) for p in srv.deny_tools):
                continue
            exposed_name = expose_name(srv.name, name)
            risk = cfg.risk_overrides.get(exposed_name) or default_risk(tool)
            limit = srv.scopes.max_risk
            if limit is not None and RISK_ORDER.index(risk) > RISK_ORDER.index(limit):
                continue
            shown = dict(tool)
            shown["name"] = exposed_name
            shown["description"] = describe(srv.name, tool.get("description"))
            self.guard.tool_risk[exposed_name] = risk
            out[exposed_name] = Exposed(srv.name, name, shown, risk, tool_pin_hash(tool))
        return out

    async def _report(
        self, rule_id: str, severity: str, tool: str, blocking: bool, digest: str, message: str
    ) -> None:
        """One decision record per distinct event (not on every refresh)."""
        key = (rule_id, tool, digest)
        if key in self._reported:
            return
        self._reported.add(key)
        policy = self.guard.policy
        mode = cast(Literal["shadow", "enforce"], self.guard.mode or policy.mode)
        await self.guard.emit(
            DecisionRecord(
                id=new_id("gdc"),
                ts=self.guard.clock(),
                session_id="mcp-gateway",
                agent_id=self.guard.agent_id,
                policy_id=policy.id,
                policy_version=policy.version,
                mode=mode,
                kind="tool_call",
                tool=tool,
                action="block" if blocking else "log",
                enforced=blocking,
                rule_id=rule_id,
                severity=severity,  # type: ignore[arg-type]
                message=message,
            )
        )

    async def _notify(self) -> None:
        for key, (ctx_session, _) in list(self._client_sessions.items()):
            try:
                await ctx_session.send_tool_list_changed()
                self.notifications_sent += 1
            except Exception:
                self._client_sessions.pop(key, None)

    # -- handlers ---------------------------------------------------------------------------

    @staticmethod
    def connection_key(ctx: Any) -> str:
        """Which client connection a request belongs to. The 2026-07-28 protocol has no
        connection object (`ctx.session` and its connection are rebuilt per request), so this
        uses the HTTP `mcp-session-id` header when there is one, else the peer address and
        user agent, and a single shared key on stdio (one client per gateway process)."""
        headers = getattr(getattr(ctx, "request", None), "headers", None)
        if headers is None:
            return "default"
        sid = headers.get("mcp-session-id")
        if sid:
            return f"sid:{sid}"
        client = getattr(ctx.request, "client", None)
        return f"peer:{getattr(client, 'host', '')}|{headers.get('user-agent', '')}"

    def _session(self, ctx: ServerRequestContext[Any]) -> Session:
        key = self.connection_key(ctx)
        entry = self._client_sessions.get(key)
        guard_session = entry[1] if entry is not None else self.guard.session()
        self._client_sessions[key] = (ctx.session, guard_session)  # keep the latest channel
        return guard_session

    async def _on_list_tools(
        self, ctx: ServerRequestContext[Any], params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        self._session(ctx)
        await self.refresh(notify=False)
        tools = [types.Tool.model_validate(e.tool) for _, e in sorted(self._exposed.items())]
        return types.ListToolsResult(tools=tools)

    @staticmethod
    def _error(text: str) -> types.CallToolResult:
        return types.CallToolResult(content=[types.TextContent(text=text)], is_error=True)

    async def _on_call_tool(
        self, ctx: ServerRequestContext[Any], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        name = params.name
        try:
            split_exposed(name, {s.name for s in self.config.servers})
        except UnknownTool:
            raise MCPError(types.INVALID_PARAMS, f"Unknown tool: {name}") from None
        entry = self._exposed.get(name)
        if entry is None:  # hidden, denied or pin-blocked: behaves as absent
            raise MCPError(types.INVALID_PARAMS, f"Unknown tool: {name}")
        session = self._session(ctx)
        args: dict[str, Any] = dict(params.arguments or {})
        call_id = new_id("call")
        decision = await session.check_tool_call(name, args, call_id=call_id)
        if decision.action == "block":
            return self._error(
                json.dumps({"error": "blocked_by_policy", "message": decision.message})
            )
        if decision.modified and isinstance(decision.modified.get("args"), dict):
            args = decision.modified["args"]
        client = self._clients[entry.server]
        trust = self.config.server(entry.server).trust
        try:
            result = await client.call_tool(entry.original, args)
        except Exception as e:
            await session.record_tool_result(
                call_id, name, {"error": type(e).__name__}, ok=False,
                untrusted=trust == "untrusted", source=entry.server,
            )  # fmt: skip
            return self._error(f"upstream error: {type(e).__name__}")
        text = "\n".join(c.text for c in result.content if isinstance(c, types.TextContent))
        await session.record_tool_result(
            call_id, name, text or result.structured_content, ok=not result.is_error,
            untrusted=trust == "untrusted", source=entry.server,
        )  # fmt: skip
        return result

    # -- serving ----------------------------------------------------------------------------

    def _init_options(self) -> Any:
        return self.server.create_initialization_options(NotificationOptions(tools_changed=True))

    async def serve_stdio(self) -> None:
        from mcp.server.stdio import stdio_server

        async with self, stdio_server() as (read, write):
            await self.server.run(read, write, self._init_options())

    async def serve_http(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        import uvicorn

        app = self.server.streamable_http_app(host=host)
        async with self:
            await uvicorn.Server(
                uvicorn.Config(app, host=host, port=port, log_level="error")
            ).serve()


async def fetch_tools(
    config: McpGatewayConfig, *, targets: Mapping[str, Any] | None = None
) -> dict[str, tuple[list[dict[str, Any]], dict[str, Any] | None]]:
    """Connect to every configured upstream, list its tools (no tool is ever called) and
    return `{server: (tool dicts, server_info)}`. Used by `gauntlet mcp pin` and `mcp diff`."""
    out: dict[str, tuple[list[dict[str, Any]], dict[str, Any] | None]] = {}
    for srv in config.servers:
        target = (targets or {}).get(srv.name) or McpGateway._target(srv)
        async with Client(target) as client:
            tools: list[dict[str, Any]] = []
            cursor: str | None = None
            while True:
                page = await client.list_tools(cursor=cursor)
                tools += [
                    t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in page.tools
                ]
                cursor = page.next_cursor
                if not cursor:
                    break
            info = client.server_info
            out[srv.name] = (
                tools,
                {"name": info.name, "version": info.version} if info is not None else None,
            )
    return out
