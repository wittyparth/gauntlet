"""MCP server wiring: `gauntlet-mcp` (stdio) or `gauntlet-mcp --http` (streamable HTTP).

The API key comes from `GAUNTLET_API_KEY` (stdio), or per request from an `Authorization: Bearer`
header on the HTTP transport, where it is required: the server's own key is never used for an
anonymous HTTP caller. The server holds no other credentials.
"""

from __future__ import annotations

import argparse
from typing import Any

from mcp.server.mcpserver import Context, MCPServer

from gauntlet_mcp import tools
from gauntlet_mcp.client import ApiError, Client


def _client_for(base: Client, ctx: Context, *, require_header: bool = False) -> Client:
    headers = ctx.headers
    auth = (headers or {}).get("authorization", "")
    if auth.lower().startswith("bearer "):
        return base.with_key(auth[7:].strip())
    if require_header:  # HTTP transport: never lend the server's own key to an anonymous caller
        raise ApiError(401, "send an Authorization: Bearer header")
    return base


def build_server(client: Client | None = None, *, require_header: bool = False) -> MCPServer:
    base = client or Client()

    def who(ctx: Context) -> Client:
        return _client_for(base, ctx, require_header=require_header)

    server = MCPServer(
        "gauntlet",
        instructions="Drive a Gauntlet platform: read runs, findings, policies; start capped runs.",
    )

    @server.tool(description="List agents in the workspace.")
    async def list_agents(ctx: Context, limit: int = 50) -> str:
        return await tools.list_agents(who(ctx), limit)

    @server.tool(description="List runs, optionally by agent version or status.")
    async def list_runs(
        ctx: Context, agent_version_id: str = "", status: str = "", limit: int = 50
    ) -> str:
        return await tools.list_runs(who(ctx), agent_version_id, status, limit)

    @server.tool(description="Get a run's report (summary, intervals, findings).")
    async def get_run_report(ctx: Context, run_id: str) -> str:
        return await tools.get_run_report(who(ctx), run_id)

    @server.tool(description="Get one episode (size-capped excerpt).")
    async def get_episode(ctx: Context, episode_id: str) -> str:
        return await tools.get_episode(who(ctx), episode_id)

    @server.tool(description="List findings, filterable by severity, status, agent version.")
    async def list_findings(
        ctx: Context,
        severity: str = "",
        status: str = "",
        agent_version_id: str = "",
        limit: int = 50,
    ) -> str:
        return await tools.list_findings(
            who(ctx),
            severity,
            status,
            agent_version_id,
            limit,
        )

    @server.tool(description="Get one finding with its evidence summary.")
    async def get_finding(ctx: Context, finding_id: str) -> str:
        return await tools.get_finding(who(ctx), finding_id)

    @server.tool(description="Ask the platform to generate scenarios for an agent.")
    async def generate_scenarios(ctx: Context, agent_id: str) -> str:
        return await tools.generate_scenarios(who(ctx), agent_id)

    @server.tool(description="Compare a run with a baseline run (default: its own baseline).")
    async def compare_runs(ctx: Context, run_id: str, baseline_run_id: str = "") -> str:
        return await tools.compare_runs(who(ctx), run_id, baseline_run_id)

    @server.tool(description="List policies (read only; this server never changes or publishes).")
    async def list_policies(ctx: Context) -> str:
        return await tools.list_policies(who(ctx))

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
            who(ctx),
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
    server = build_server(require_header=args.http)
    kw: dict[str, Any] = {"host": args.host, "port": args.port} if args.http else {}
    server.run("streamable-http" if args.http else "stdio", **kw)


if __name__ == "__main__":
    main()
