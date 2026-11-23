"""MCP server wiring: `gauntlet-mcp` (stdio) or `gauntlet-mcp --http` (streamable HTTP).

The API key comes from `GAUNTLET_API_KEY`, or per request from an `Authorization: Bearer` header
on the HTTP transport. The server holds no other credentials.
"""

from __future__ import annotations

import argparse
from typing import Any

from mcp.server.mcpserver import Context, MCPServer

from gauntlet_mcp import tools
from gauntlet_mcp.client import Client


def _client_for(base: Client, ctx: Context) -> Client:
    headers = ctx.headers
    auth = (headers or {}).get("authorization", "")
    if auth.lower().startswith("bearer "):
        return base.with_key(auth[7:].strip())
    return base


def build_server(client: Client | None = None) -> MCPServer:
    base = client or Client()
    server = MCPServer(
        "gauntlet",
        instructions="Drive a Gauntlet platform: read runs, findings, policies; start capped runs.",
    )

    @server.tool(description="List agents in the workspace.")
    async def list_agents(ctx: Context, limit: int = 50) -> str:
        return await tools.list_agents(_client_for(base, ctx), limit)

    @server.tool(description="List runs, optionally by agent version or status.")
    async def list_runs(
        ctx: Context, agent_version_id: str = "", status: str = "", limit: int = 50
    ) -> str:
        return await tools.list_runs(_client_for(base, ctx), agent_version_id, status, limit)

    @server.tool(description="Get a run's report (summary, intervals, findings).")
    async def get_run_report(ctx: Context, run_id: str) -> str:
        return await tools.get_run_report(_client_for(base, ctx), run_id)

    @server.tool(description="Get one episode (size-capped excerpt).")
    async def get_episode(ctx: Context, episode_id: str) -> str:
        return await tools.get_episode(_client_for(base, ctx), episode_id)

    @server.tool(description="List findings, filterable by severity, status, agent version.")
    async def list_findings(
        ctx: Context,
        severity: str = "",
        status: str = "",
        agent_version_id: str = "",
        limit: int = 50,
    ) -> str:
        return await tools.list_findings(
            _client_for(base, ctx), severity, status, agent_version_id, limit
        )

    @server.tool(description="Get one finding with its evidence summary.")
    async def get_finding(ctx: Context, finding_id: str) -> str:
        return await tools.get_finding(_client_for(base, ctx), finding_id)

    @server.tool(description="Ask the platform to generate scenarios for an agent.")
    async def generate_scenarios(ctx: Context, agent_id: str) -> str:
        return await tools.generate_scenarios(_client_for(base, ctx), agent_id)

    @server.tool(description="Compare a run with a baseline run (default: its own baseline).")
    async def compare_runs(ctx: Context, run_id: str, baseline_run_id: str = "") -> str:
        return await tools.compare_runs(_client_for(base, ctx), run_id, baseline_run_id)

    @server.tool(description="List policies (read only; this server never changes or publishes).")
    async def list_policies(ctx: Context) -> str:
        return await tools.list_policies(_client_for(base, ctx))

    @server.tool(
        description=(
            "Start a run. Spends money: requires confirm=true and budget_usd within "
            "GAUNTLET_MCP_MAX_BUDGET_USD (default 1.0)."
        )
    )
    async def create_run(
        ctx: Context,
        suite_id: str,
        agent_version_id: str,
        budget_usd: float | None = None,
        confirm: bool = False,
        repetitions: int | None = None,
        seed: int | None = None,
    ) -> str:
        return await tools.create_run(
            _client_for(base, ctx),
            suite_id,
            agent_version_id,
            budget_usd,
            confirm,
            repetitions,
            seed,
        )

    return server


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="gauntlet-mcp", description=__doc__)
    p.add_argument("--http", action="store_true", help="serve streamable HTTP instead of stdio")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args(argv)
    server = build_server()
    kw: dict[str, Any] = {"host": args.host, "port": args.port} if args.http else {}
    server.run("streamable-http" if args.http else "stdio", **kw)


if __name__ == "__main__":
    main()
