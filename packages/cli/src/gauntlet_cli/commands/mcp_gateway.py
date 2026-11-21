"""`gauntlet mcp-gateway serve`, `gauntlet mcp pin` and `gauntlet mcp diff` (P4-3).

Pinning connects to the configured upstream servers and lists their tools; it never calls one.
"""

from __future__ import annotations

import asyncio
import getpass
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml
from gauntlet_core.gateway import Guard, JsonlSink
from gauntlet_core.gateway.mcp import McpGateway, McpGatewayConfig, PinStore, fetch_tools
from pydantic import ValidationError

__all__ = ["mcp_app", "mcp_gateway_app"]

mcp_gateway_app = typer.Typer(help="Run the MCP gateway.", no_args_is_help=True)
mcp_app = typer.Typer(help="Pin and diff upstream MCP tool definitions.", no_args_is_help=True)

ConfigOpt = Annotated[Path, typer.Option("--config", help="gateway.yaml.")]
PinsOpt = Annotated[Path | None, typer.Option("--pins", help="pins.json (default: from config).")]


def _load(config: Path, pins: Path | None) -> tuple[McpGatewayConfig, Path]:
    try:
        cfg = McpGatewayConfig.load(config)
    except (OSError, ValueError, ValidationError, yaml.YAMLError) as e:
        typer.echo(f"{config}: {str(e).splitlines()[0]}", err=True)
        raise typer.Exit(2) from e
    return cfg, pins or Path(cfg.pins)


def _fetch(cfg: McpGatewayConfig) -> dict[str, tuple[list[dict[str, Any]], dict[str, Any] | None]]:
    try:
        return asyncio.run(fetch_tools(cfg))
    except BaseException as e:
        if isinstance(e, KeyboardInterrupt | SystemExit):
            raise
        typer.echo(f"cannot list upstream tools: {type(e).__name__}: {e}", err=True)
        raise typer.Exit(2) from e


@mcp_gateway_app.command("serve")
def serve(
    config: ConfigOpt,
    http: Annotated[
        str | None, typer.Option("--http", help="Serve streamable HTTP on HOST:PORT (else stdio).")
    ] = None,
    pins: PinsOpt = None,
    decisions: Annotated[
        Path | None, typer.Option("--decisions", help="Append decision records here (JSONL).")
    ] = None,
) -> None:
    """Serve one MCP server to the agent client, in front of the configured upstreams."""
    cfg, pins_path = _load(config, pins)
    try:
        guard = (
            Guard(cfg.policy, mode=cfg.mode, sink=JsonlSink(decisions) if decisions else None)
            if cfg.policy
            else None
        )
    except (OSError, ValueError, ValidationError, yaml.YAMLError) as e:
        typer.echo(f"policy: {str(e).splitlines()[0]}", err=True)
        raise typer.Exit(2) from e
    if guard is None:
        from gauntlet_core.schema import Policy

        guard = Guard(
            Policy(id="mcp-gateway", rules=[]),
            mode=cfg.mode or "enforce",
            sink=JsonlSink(decisions) if decisions else None,
        )
    gateway = McpGateway(cfg, guard, pins=PinStore.load(pins_path))
    if http:
        host, _, port = http.rpartition(":")
        if not host or not port.isdigit():
            typer.echo("--http must look like HOST:PORT", err=True)
            raise typer.Exit(2)
        asyncio.run(gateway.serve_http(host, int(port)))
    else:
        asyncio.run(gateway.serve_stdio())  # stdout belongs to the protocol: nothing else prints


@mcp_app.command("pin")
def pin(
    config: ConfigOpt,
    approve_all: Annotated[
        bool, typer.Option("--approve-all", help="Approve every tool of every server.")
    ] = False,
    tool: Annotated[
        list[str] | None, typer.Option("--tool", help="server/tool to approve, repeatable.")
    ] = None,
    pins: PinsOpt = None,
    approved_by: Annotated[str | None, typer.Option(help="Recorded as the approver.")] = None,
) -> None:
    """Approve the current tool definitions of the upstream servers (writes pins.json)."""
    if approve_all == bool(tool):
        typer.echo("give exactly one of --approve-all or --tool server/tool", err=True)
        raise typer.Exit(2)
    cfg, pins_path = _load(config, pins)
    wanted: dict[str, set[str]] = {}
    for item in tool or []:
        server, sep, name = item.partition("/")
        if not sep or not name or server not in {s.name for s in cfg.servers}:
            typer.echo(
                f"--tool must look like server/tool for a configured server: {item!r}", err=True
            )
            raise typer.Exit(2)
        wanted.setdefault(server, set()).add(name)
    listings = _fetch(cfg)
    store = PinStore.load(pins_path)
    who = approved_by or getpass.getuser()
    approved = 0
    for server, (tools, info) in listings.items():
        if not approve_all and server not in wanted:
            continue
        names = {t["name"] for t in tools}
        missing = wanted.get(server, set()) - names
        if missing:
            typer.echo(f"{server} offers no tool {', '.join(sorted(missing))}", err=True)
            raise typer.Exit(2)
        store.approve(
            server, tools, only=None if approve_all else sorted(wanted[server]),
            approved_by=who, server_info=info,
        )  # fmt: skip
        approved += len(names) if approve_all else len(wanted[server])
    store.save(pins_path)
    typer.echo(f"approved {approved} tool(s); pins written to {pins_path}")


@mcp_app.command("diff")
def diff(config: ConfigOpt, pins: PinsOpt = None) -> None:
    """Compare the upstream tool definitions with the approved pins (exit 1 on any difference)."""
    cfg, pins_path = _load(config, pins)
    store = PinStore.load(pins_path)
    dirty = False
    for server, (tools, _) in _fetch(cfg).items():
        report = store.check(server, tools)
        for st in report.tools:
            typer.echo(f"{server}/{st.tool}: {st.status}")
            if st.diff:
                typer.echo(st.diff)
        dirty = dirty or not report.clean
    raise typer.Exit(1 if dirty else 0)
