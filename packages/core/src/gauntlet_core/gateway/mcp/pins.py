"""Tool pinning, the rug-pull defence (P4-3).

Hash recipe, exactly: take `{"name", "title", "description", "inputSchema", "outputSchema",
"annotations"}` using only the keys the server returned (a missing key is omitted, not null);
`title` and `description` get Unicode NFC and nothing else (invisible characters are kept, so a
zero-width character changes the hash); serialise with
`json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`, encode UTF-8,
`"sha256:" + sha256(bytes).hexdigest()`.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

__all__ = [
    "PIN_KEYS",
    "PinReport",
    "PinStore",
    "ToolPinStatus",
    "canonical_tool",
    "server_manifest_hash",
    "tool_pin_hash",
]

PIN_KEYS = ("name", "title", "description", "inputSchema", "outputSchema", "annotations")
Status = Literal["unchanged", "changed", "new", "removed"]


def canonical_tool(tool: Mapping[str, Any]) -> str:
    obj: dict[str, Any] = {}
    for key in PIN_KEYS:
        if key not in tool:
            continue
        value = tool[key]
        if key in ("title", "description") and isinstance(value, str):
            value = unicodedata.normalize("NFC", value)
        obj[key] = value
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def tool_pin_hash(tool: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_tool(tool).encode("utf-8")).hexdigest()


def server_manifest_hash(tool_hashes: Mapping[str, str]) -> str:
    lines = "".join(f"{name}\t{tool_hashes[name]}\n" for name in sorted(tool_hashes))
    return "sha256:" + hashlib.sha256(lines.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ToolPinStatus:
    tool: str
    status: Status
    hash: str | None  # the current hash (None for removed)
    pinned_hash: str | None
    diff: str = ""  # unified diff of the canonical JSON, for changed tools


@dataclass
class PinReport:
    server: str
    tools: list[ToolPinStatus] = field(default_factory=list)

    def _of(self, status: Status) -> list[str]:
        return [t.tool for t in self.tools if t.status == status]

    @property
    def changed(self) -> list[str]:
        return self._of("changed")

    @property
    def new(self) -> list[str]:
        return self._of("new")

    @property
    def removed(self) -> list[str]:
        return self._of("removed")

    @property
    def unchanged(self) -> list[str]:
        return self._of("unchanged")

    @property
    def clean(self) -> bool:
        return not (self.changed or self.new or self.removed)

    def status_of(self, tool: str) -> Status | None:
        return next((t.status for t in self.tools if t.tool == tool), None)


def _pretty(canonical: str) -> list[str]:
    try:
        return json.dumps(json.loads(canonical), indent=2, sort_keys=True).splitlines()
    except ValueError:
        return [canonical]


class PinStore:
    """`pins.json`: `{"version": 1, "servers": {name: {"manifest", "server_info", "approved_at",
    "approved_by", "tools": {tool: {"hash", "approved_at", "canonical"}}}}}`. `canonical` (the
    canonical JSON, additive to the documented format) lets `diff` show what changed."""

    def __init__(self, data: dict[str, Any] | None = None, path: Path | None = None) -> None:
        self.data: dict[str, Any] = data or {"version": 1, "servers": {}}
        self.path = path

    @classmethod
    def load(cls, path: str | Path) -> PinStore:
        p = Path(path)
        if not p.exists():
            return cls(path=p)
        data = json.loads(p.read_text())
        if data.get("version") != 1:
            raise ValueError(f"{p}: unsupported pins version {data.get('version')!r}")
        return cls(data, p)

    def save(self, path: str | Path | None = None) -> None:
        target = Path(path) if path else self.path
        if target is None:
            raise ValueError("no path to save the pins to")
        target.write_text(json.dumps(self.data, indent=2, sort_keys=True) + "\n")
        self.path = target

    def servers(self) -> list[str]:
        return sorted(self.data["servers"])

    def pinned(self, server: str) -> dict[str, str]:
        tools = self.data["servers"].get(server, {}).get("tools", {})
        return {name: t["hash"] for name, t in tools.items()}

    def check(self, server: str, tools: Iterable[Mapping[str, Any]]) -> PinReport:
        entry = self.data["servers"].get(server, {}).get("tools", {})
        report = PinReport(server)
        seen: set[str] = set()
        for tool in tools:
            name = str(tool["name"])
            seen.add(name)
            h = tool_pin_hash(tool)
            pin = entry.get(name)
            if pin is None:
                report.tools.append(ToolPinStatus(name, "new", h, None))
            elif pin["hash"] == h:
                report.tools.append(ToolPinStatus(name, "unchanged", h, h))
            else:
                old = _pretty(pin.get("canonical", ""))
                new = _pretty(canonical_tool(tool))
                diff = "\n".join(difflib.unified_diff(old, new, "pinned", "current", lineterm=""))
                report.tools.append(ToolPinStatus(name, "changed", h, pin["hash"], diff))
        for name in sorted(set(entry) - seen):
            report.tools.append(ToolPinStatus(name, "removed", None, entry[name]["hash"]))
        return report

    def approve(
        self,
        server: str,
        tools: Iterable[Mapping[str, Any]],
        *,
        only: Iterable[str] | None = None,
        approved_by: str = "cli",
        server_info: Mapping[str, Any] | None = None,
        now: datetime | None = None,
    ) -> None:
        """Pin the current definitions. Without `only` the server's pins become exactly the
        given listing (removed tools drop out); with `only` just those tools are pinned."""
        stamp = (now or datetime.now(UTC)).isoformat()
        current = {str(t["name"]): t for t in tools}
        entry = self.data["servers"].setdefault(server, {"tools": {}})
        if only is None:
            entry["tools"] = {}
            names = list(current)
        else:
            names = [n for n in only if n in current]
        for name in names:
            tool = current[name]
            entry["tools"][name] = {
                "hash": tool_pin_hash(tool),
                "approved_at": stamp,
                "canonical": canonical_tool(tool),
            }
        entry["manifest"] = server_manifest_hash({n: t["hash"] for n, t in entry["tools"].items()})
        entry["approved_at"] = stamp
        entry["approved_by"] = approved_by
        if server_info is not None:
            entry["server_info"] = dict(server_info)  # recorded, never part of a hash
