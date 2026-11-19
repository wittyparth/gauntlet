"""Taint markers (hard-cores 6.3). A marker is a unique high-entropy token an injected payload
carries in the place an attacker would put their own data. The world discovers them by shape,
so the injection harness needs no side channel into `build_world`."""

from __future__ import annotations

import json
import re
from typing import Any

MARKER_RE = re.compile(r"gmk-[0-9a-f]{12}")
INJECT_PREFIX = "inject:"  # DocumentSpec id prefix: its body is appended to that tool's results


def scan_markers(*objs: Any) -> list[str]:
    """Markers found anywhere in the JSON-able objects, in first-seen order."""
    found: list[str] = []
    for obj in objs:
        for m in MARKER_RE.findall(json.dumps(obj, default=str)):
            if m not in found:
                found.append(m)
    return found


def append_injection(result: Any, bodies: list[str]) -> Any:
    """What the agent sees when a tool's result carries injected third-party content."""
    text = "\n".join(bodies)
    if isinstance(result, dict):
        return {**result, "external_content": text}
    if isinstance(result, str):
        return f"{result}\n{text}"
    return {"result": result, "external_content": text}
