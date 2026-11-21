"""Small helpers over the mock world's `run_sql` and `describe_schema` tools."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

__all__ = ["Call", "dump_rows", "query"]

Call = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


async def query(call: Call, sql: str) -> dict[str, Any]:
    """`{"ok": bool, "result": {...} | None, "error": str | None}` from the mock tool."""
    return await call("run_sql", {"query": sql})


def dump_rows(res: dict[str, Any]) -> str:
    rows = (res.get("result") or {}).get("rows", [])
    return json.dumps(rows, default=str)
