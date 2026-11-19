"""`gauntlet scan mcp`: read-only security scan of an MCP server's tool listing.

Scan only servers you are allowed to connect to. The scanner performs a normal client handshake
and lists tools, resources and prompts; it never calls a tool.
"""

from __future__ import annotations

import asyncio
import json
import shlex
from pathlib import Path
from typing import Annotated

import typer
from gauntlet_core.security.scan import (
    SEVERITY_RANK,
    TransportInfo,
    exceeds,
    render,
    scan_mcp_tools,
)

from ..mcp_client import ConnectError, fetch_listing

__all__ = ["scan_app"]

scan_app = typer.Typer(help="Scan things for security problems.", no_args_is_help=True)


def _kv(items: list[str], sep: str, what: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items:
        k, s, v = item.partition(sep)
        if not s or not k.strip():
            typer.echo(f"{what} must look like KEY{sep}VALUE: {item!r}", err=True)
            raise typer.Exit(2)
        out[k.strip()] = v.strip()
    return out


@scan_app.command("mcp")
def scan_mcp(
    stdio: Annotated[str | None, typer.Option(help="Command that starts a stdio server.")] = None,
    url: Annotated[str | None, typer.Option(help="Streamable HTTP endpoint.")] = None,
    tools_file: Annotated[
        Path | None, typer.Option(help="Saved tools/list JSON (offline).")
    ] = None,
    header: Annotated[list[str] | None, typer.Option("--header", help="K:V, repeatable.")] = None,
    env: Annotated[list[str] | None, typer.Option("--env", help="K=V, repeatable.")] = None,
    fmt: Annotated[str, typer.Option("--format", help="text, json or sarif.")] = "text",
    fail_on: Annotated[str, typer.Option(help="low, medium, high or critical.")] = "high",
    timeout: Annotated[float, typer.Option(help="Seconds.")] = 20.0,
) -> None:
    """Scan an MCP server (exit 0 clean, 1 findings at or above --fail-on, 2 usage or error)."""
    if sum(x is not None for x in (stdio, url, tools_file)) != 1:
        typer.echo("give exactly one of --stdio, --url, --tools-file", err=True)
        raise typer.Exit(2)
    if fail_on not in SEVERITY_RANK or fmt not in {"text", "json", "sarif"}:
        typer.echo("bad --fail-on or --format", err=True)
        raise typer.Exit(2)
    if tools_file is not None:
        try:
            data = json.loads(tools_file.read_text())
        except (OSError, ValueError) as e:
            typer.echo(f"cannot read {tools_file}: {e}", err=True)
            raise typer.Exit(2) from e
        listing = data.get("result", data) if isinstance(data, dict) else {}
        transport = TransportInfo()
    else:
        try:
            listing, transport = asyncio.run(
                fetch_listing(
                    stdio=shlex.split(stdio) if stdio else None,
                    url=url,
                    headers=_kv(header or [], ":", "--header"),
                    env=_kv(env or [], "=", "--env"),
                    timeout=timeout,
                )
            )
        except ConnectError as e:
            typer.echo(f"connection failed: {e}", err=True)
            raise typer.Exit(2) from e
    findings = scan_mcp_tools(listing, transport=transport)
    out = render(findings, fmt, tool="gauntlet-mcp-scan")
    if out:
        typer.echo(out)
    raise typer.Exit(1 if exceeds(findings, fail_on) else 0)
