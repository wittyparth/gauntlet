"""Registry of deterministic detectors for the `detector` node (decision CQ-B4).

A detector inspects a trajectory and reports whether it fires, with evidence. The actual
detectors (pii, secret, ...) live elsewhere and register themselves here.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from typing import Any

from gauntlet_core.schema import CheckResult, Evidence, Json, Trajectory

from ..support import snippet

DetectorFn = Callable[[Trajectory, Mapping[str, Json]], CheckResult]

_REGISTRY: dict[str, DetectorFn] = {}


def register(name: str) -> Callable[[DetectorFn], DetectorFn]:
    """Decorator: `@register("pii")`. Names are unique."""

    def deco(fn: DetectorFn) -> DetectorFn:
        if name in _REGISTRY and _REGISTRY[name] is not fn:
            raise ValueError(f"detector {name!r} is already registered")
        _REGISTRY[name] = fn
        return fn

    return deco


def get(name: str) -> DetectorFn:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"unknown detector {name!r}; registered: {names()}") from None


def names() -> list[str]:
    return sorted(_REGISTRY)


def _string_leaves(v: Any) -> Iterator[str]:
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from _string_leaves(x)
    elif isinstance(v, list | tuple):
        for x in v:
            yield from _string_leaves(x)


def text_detector(
    fn: Callable[[str, Mapping[str, Any]], list[tuple[int, int]]],
) -> DetectorFn:
    """Lift a text-level detector (text, params) -> list of (start, end) spans into a
    DetectorFn that scans agent messages and the string values in tool-call args. Each span
    becomes one Evidence quoting the matched text."""

    def detect(traj: Trajectory, params: Mapping[str, Json]) -> CheckResult:
        evidence: list[Evidence] = []
        for e in traj.events:
            if e.kind == "agent_message":
                texts = [str(e.payload.get("text", ""))]
            elif e.kind == "tool_call":
                texts = list(_string_leaves(e.payload.get("args", {})))
            else:
                continue
            for text in texts:
                for start, end in fn(text, params):
                    evidence.append(Evidence(seq=e.seq, quote=snippet(text, start, end)))
        return CheckResult(holds=bool(evidence), evidence=evidence)

    return detect
