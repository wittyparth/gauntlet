"""Result shaping: drop secret-looking fields and cap the serialised size (default 20 KB)."""

from __future__ import annotations

import json
import os
import re
from typing import Any

DEFAULT_CAP_BYTES = 20_000
MARKER = "\n...[truncated by gauntlet-mcp: result exceeded the size cap]"
_SECRET = re.compile(
    r"(secret|token|password|passwd|api[_-]?key|authorization|credential|private[_-]?key)", re.I
)


def max_bytes() -> int:
    try:
        return int(os.environ.get("GAUNTLET_MCP_MAX_BYTES", DEFAULT_CAP_BYTES))
    except ValueError:
        return DEFAULT_CAP_BYTES


def strip_secrets(value: Any) -> Any:
    """Remove every dict key that looks like a credential, at any depth."""
    if isinstance(value, dict):
        return {k: strip_secrets(v) for k, v in value.items() if not _SECRET.search(str(k))}
    if isinstance(value, list):
        return [strip_secrets(v) for v in value]
    return value


def cap(value: Any, limit: int | None = None) -> str:
    """JSON text of `value` without secret fields, truncated with a marker above `limit`."""
    limit = limit or max_bytes()
    text = json.dumps(strip_secrets(value), indent=1, default=str)
    raw = text.encode()
    if len(raw) <= limit:
        return text
    return raw[:limit].decode(errors="ignore") + MARKER
