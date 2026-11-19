"""Shared types for the MCP scanner and the agent linter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = [
    "SEVERITY_RANK",
    "ScanFinding",
    "TransportInfo",
    "at_least",
    "excerpt",
]

SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
Severity = Literal["low", "medium", "high", "critical"]


@dataclass(frozen=True)
class ScanFinding:
    rule_id: str
    severity: Severity
    title: str
    detail: str
    location: str  # tool name (MCP) or `path:line` (lint)
    evidence: str
    category: str


@dataclass(frozen=True)
class TransportInfo:
    """Facts about how the server was reached (offline listings have `kind='file'`)."""

    kind: Literal["stdio", "http", "file"] = "file"
    url: str | None = None
    has_credentials: bool = False  # an Authorization header (or similar) was sent
    connected_without_auth: bool = False  # handshake and tools/list worked unauthenticated


def excerpt(text: str, start: int = 0, width: int = 120) -> str:
    """A single-line excerpt of at most `width` characters starting near `start`."""
    lo = max(0, start - 20)
    return " ".join(text[lo : lo + width].split())[:width]


def at_least(severity: str, threshold: str) -> bool:
    return SEVERITY_RANK[severity] >= SEVERITY_RANK[threshold]
