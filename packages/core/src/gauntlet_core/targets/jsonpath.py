"""The tiny dotted-path language used by HTTP targets: `a.b[0].c`. No wildcards."""

from __future__ import annotations

import re
from typing import Any

__all__ = ["MISSING", "get_path", "set_path"]


class _Missing:
    def __repr__(self) -> str:
        return "MISSING"

    def __bool__(self) -> bool:
        return False


MISSING: Any = _Missing()
_PART = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def _parse(path: str) -> list[str | int]:
    parts: list[str | int] = []
    for m in _PART.finditer(path):
        parts.append(m.group(1) if m.group(1) is not None else int(m.group(2)))
    return parts


def get_path(obj: Any, path: str) -> Any:
    """Value at `path`, or the MISSING sentinel (never None) when any step is absent."""
    cur = obj
    for p in _parse(path):
        if isinstance(p, int):
            if not isinstance(cur, list) or p >= len(cur):
                return MISSING
            cur = cur[p]
        else:
            if not isinstance(cur, dict) or p not in cur:
                return MISSING
            cur = cur[p]
    return cur


def set_path(obj: dict[str, Any], path: str, value: Any) -> None:
    """Set `path` in place, creating dicts and padding lists with None as needed."""
    parts = _parse(path)
    if not parts:
        raise ValueError("empty path")
    cur: Any = obj
    for i, p in enumerate(parts):
        last = i == len(parts) - 1
        nxt: Any = value if last else ([] if isinstance(parts[i + 1], int) else {})
        if isinstance(p, int):
            while len(cur) <= p:
                cur.append(None)
            if last or not isinstance(cur[p], dict | list):
                cur[p] = nxt
            cur = cur[p]
        else:
            if last or not isinstance(cur.get(p), dict | list):
                cur[p] = nxt
            cur = cur[p]
