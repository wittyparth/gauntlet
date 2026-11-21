"""Description scanning before exposure (P4-3): MCP-001 to MCP-008 and MCP-011 from the P2-8
scanner. Findings at or above `block_at` hide the tool."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from gauntlet_core.security.scan import SEVERITY_RANK, ScanFinding, scan_mcp_tools

from .pins import tool_pin_hash

__all__ = ["SCANNED_RULES", "ScanHook"]

SCANNED_RULES = frozenset({f"MCP-{n:03d}" for n in (1, 2, 3, 4, 5, 6, 7, 8, 11)})
ScanFn = Callable[[dict[str, Any]], list[ScanFinding]]


class ScanHook:
    """Scans a server's tool listing. Results are cached on the tuple of tool hashes, so an
    unchanged listing is never scanned twice (a changed tool changes its hash)."""

    def __init__(self, block_at: str = "high", scan_fn: ScanFn | None = None) -> None:
        self.block_at = block_at
        self._scan = scan_fn or (lambda listing: scan_mcp_tools(listing))
        self._cache: dict[tuple[str, ...], list[ScanFinding]] = {}
        self.scans = 0

    def findings(self, tools: Sequence[Mapping[str, Any]]) -> list[ScanFinding]:
        key = tuple(sorted(tool_pin_hash(t) for t in tools))
        hit = self._cache.get(key)
        if hit is None:
            self.scans += 1
            raw = self._scan({"tools": [dict(t) for t in tools]})
            hit = [f for f in raw if f.rule_id in SCANNED_RULES]
            self._cache[key] = hit
        return hit

    def blocked(self, tools: Sequence[Mapping[str, Any]]) -> dict[str, list[ScanFinding]]:
        """Tool name -> its findings at or above `block_at` (server-level findings, whose
        location is not a tool name, never hide a tool)."""
        names = {str(t["name"]) for t in tools}
        out: dict[str, list[ScanFinding]] = {}
        for f in self.findings(tools):
            if f.location in names and SEVERITY_RANK[f.severity] >= SEVERITY_RANK[self.block_at]:
                out.setdefault(f.location, []).append(f)
        return out
