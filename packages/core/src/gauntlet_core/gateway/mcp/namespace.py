"""Namespace isolation (P4-3): tools reach the agent as `<server>__<tool>`."""

from __future__ import annotations

import logging
from collections.abc import Collection

__all__ = ["SEP", "UnknownTool", "describe", "expose_name", "split_exposed"]

SEP = "__"
log = logging.getLogger("gauntlet.gateway.mcp")


class UnknownTool(LookupError):
    """The exposed name has no known namespace prefix (reported as JSON-RPC -32602)."""


def expose_name(server: str, tool: str) -> str:
    """`<server>__<tool>`. A tool name that itself contains `__` has it replaced by `_`
    (with a warning) so the first `__` always separates the server from the tool."""
    if SEP in tool:
        fixed = tool.replace(SEP, "_")
        log.warning("mcp gateway: renamed %s tool %r to %r", server, tool, fixed)
        tool = fixed
    return f"{server}{SEP}{tool}"


def split_exposed(exposed: str, servers: Collection[str]) -> tuple[str, str]:
    """`(server, remainder)` for an exposed name; UnknownTool when the prefix is not a server."""
    server, sep, rest = exposed.partition(SEP)
    if not sep or not rest or server not in servers:
        raise UnknownTool(exposed)
    return server, rest


def describe(server: str, description: str | None) -> str:
    return f"[server: {server}] {description or ''}".rstrip()
