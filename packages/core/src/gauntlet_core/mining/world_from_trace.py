"""Reconstruct the seed records a trace implies (P5-2): what the agent's read tools returned
becomes the world the mined scenario starts from."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from gauntlet_core.schema import CrudHandler, Event, WorldSpec

__all__ = ["world_from_trace"]


def world_from_trace(
    events: Sequence[Event], world: WorldSpec
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """`(world_overrides, unmapped)`: records keyed by collection, mapped through the tools'
    crud handlers; tools whose results cannot be mapped (python or llm handlers, results
    without an `id`) are listed in `unmapped`, nothing is invented."""
    tools = {t.name: t for t in world.tools}
    called: dict[str, str] = {}
    out: dict[str, dict[str, dict[str, Any]]] = {}
    unmapped: list[str] = []
    for e in events:
        if e.kind == "tool_call":
            called[str(e.payload.get("call_id"))] = str(e.payload.get("tool"))
        elif e.kind == "tool_result" and e.payload.get("ok") and e.payload.get("result"):
            tool = called.get(str(e.payload.get("call_id")))
            spec = tools.get(tool or "")
            if spec is None:
                if tool and tool not in unmapped:
                    unmapped.append(tool)
                continue
            h = spec.handler
            if not isinstance(h, CrudHandler) or h.op not in ("get", "list"):
                if tool not in unmapped:
                    unmapped.append(str(tool))
                continue
            try:
                body = json.loads(str(e.payload["result"]))
            except ValueError:
                unmapped.append(f"{tool} (result is not JSON)")
                continue
            rows = body if isinstance(body, list) else [body]
            for row in rows:
                if isinstance(row, dict) and "id" in row:
                    out.setdefault(h.collection, {})[str(row["id"])] = row
                else:
                    unmapped.append(f"{tool} (a result without an id)")
    return {c: list(r.values()) for c, r in out.items()}, sorted(set(unmapped))
