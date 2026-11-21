"""MCP gateway (P4-3): namespacing, pinning, scanning and policy interception in front of
upstream MCP servers. `McpGateway` needs the `mcp` extra (`gauntlet-core[mcp]`) and is imported
on first use."""

from typing import TYPE_CHECKING, Any

from .config import McpGatewayConfig, ScanConfig, ScopesConfig, ServerConfig
from .namespace import UnknownTool, describe, expose_name, split_exposed
from .pins import (
    PinReport,
    PinStore,
    ToolPinStatus,
    canonical_tool,
    server_manifest_hash,
    tool_pin_hash,
)
from .scan_hook import ScanHook

if TYPE_CHECKING:
    from .proxy import McpGateway

__all__ = [
    "McpGateway",
    "McpGatewayConfig",
    "PinReport",
    "PinStore",
    "ScanConfig",
    "ScanHook",
    "ScopesConfig",
    "ServerConfig",
    "ToolPinStatus",
    "UnknownTool",
    "canonical_tool",
    "describe",
    "expose_name",
    "server_manifest_hash",
    "split_exposed",
    "tool_pin_hash",
]


def __getattr__(name: str) -> Any:
    if name == "McpGateway":
        from .proxy import McpGateway

        return McpGateway
    raise AttributeError(name)
