"""Tool handlers, argument validation and fault injection. Everything here is pure:
no I/O, no clock, no randomness (the caller passes the simulated time and the dice roll)."""

from __future__ import annotations

import importlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from gauntlet_core.schema import (
    CrudHandler,
    FaultSpec,
    Json,
    PatchOp,
    PythonHandler,
    StaticHandler,
    ToolSpec,
)

from .state import WorldView


@dataclass(frozen=True)
class ToolOutcome:
    result: Any = None
    patch: list[PatchOp] = field(default_factory=list)
    error: str | None = None


ToolHandler = Callable[[WorldView, Json, datetime], ToolOutcome]


class NeedsLLM(Exception):
    """The tool is `llm_sim`: the engine must answer it through the model gateway."""


def _new_id(view: WorldView, collection: str) -> str:
    stem = collection[:-1] if collection.endswith("s") else collection
    n = view.size(collection) + 1
    while view.get(collection, f"{stem}_{n}") is not None:
        n += 1
    return f"{stem}_{n}"


def _crud(spec: CrudHandler) -> ToolHandler:
    col = spec.collection

    def handler(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
        key = str(args[spec.key_arg]) if spec.key_arg and spec.key_arg in args else None
        if spec.op == "list":
            filters = {k: args[k] for k in spec.filter_args if k in args}
            return ToolOutcome(result=view.list(col, **filters))
        if spec.op == "create":
            rec = {k: v for k, v in args.items()}
            rec["id"] = str(rec.get("id") or _new_id(view, col))
            if view.get(col, rec["id"]) is not None:
                return ToolOutcome(error="already_exists")
            return ToolOutcome(
                result=rec, patch=[PatchOp(op="add", collection=col, id=rec["id"], value=rec)]
            )
        if key is None:
            return ToolOutcome(error=f"missing_argument: {spec.key_arg}")
        cur = view.get(col, key)
        if cur is None:
            return ToolOutcome(error="not_found")
        if spec.op == "get":
            return ToolOutcome(result=cur)
        if spec.op == "delete":
            return ToolOutcome(
                result={"deleted": key},
                patch=[PatchOp(op="remove", collection=col, id=key, before=cur)],
            )
        new = {**cur, **{k: v for k, v in args.items() if k != spec.key_arg}}
        return ToolOutcome(
            result=new,
            patch=[PatchOp(op="replace", collection=col, id=key, value=new, before=cur)],
        )

    return handler


def resolve_handler(spec: ToolSpec) -> ToolHandler:
    h = spec.handler
    if isinstance(h, CrudHandler):
        return _crud(h)
    if isinstance(h, PythonHandler):
        module, _, name = h.entrypoint.partition(":")
        return getattr(importlib.import_module(module), name)
    if isinstance(h, StaticHandler):
        return lambda view, args, now: ToolOutcome(result=h.result)
    raise NeedsLLM(spec.name)


def assert_pure(handler: ToolHandler, view: WorldView, args: Json, now: datetime) -> None:
    """Test harness: a handler must return the same outcome for the same input."""
    a, b = handler(view, dict(args), now), handler(view, dict(args), now)
    if a != b:
        raise AssertionError(f"handler is not pure: {a} != {b}")


_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
}


def validate_args(schema: Json, args: Json) -> str | None:
    """Minimal JSON Schema check (required, type, enum). Returns an error string or None."""
    if not isinstance(args, dict):
        return "arguments must be an object"
    for name in schema.get("required", []):
        if name not in args:
            return f"missing required argument '{name}'"
    for name, sub in schema.get("properties", {}).items():
        if name not in args:
            continue
        value, want = args[name], sub.get("type")
        if want in _TYPES and (
            not isinstance(value, _TYPES[want])
            or (want in ("integer", "number") and isinstance(value, bool))
        ):
            return f"argument '{name}' must be {want}"
        if "enum" in sub and value not in sub["enum"]:
            return f"argument '{name}' must be one of {sub['enum']}"
    return None


def pick_fault(
    faults: list[FaultSpec], tool: str, call_index: int, roll: float
) -> FaultSpec | None:
    for f in faults:
        if (
            f.tool == tool
            and (f.on_call_index is None or f.on_call_index == call_index)
            and roll < f.probability
        ):
            return f
    return None


_ERROR_FAULTS = {"timeout": "timeout", "http_500": "http_500", "http_429": "rate_limited"}


def apply_fault(
    fault: FaultSpec, run: Callable[[], ToolOutcome], run_stale: Callable[[], ToolOutcome]
) -> tuple[ToolOutcome, int]:
    """Returns (outcome, added_latency_ms). `run` executes the real handler, `run_stale`
    executes it against the initial snapshot."""
    kind = fault.kind
    if kind in _ERROR_FAULTS:
        return ToolOutcome(error=_ERROR_FAULTS[kind]), 0
    if kind == "latency":
        return run(), int(fault.params.get("ms", 5000))
    if kind == "stale":
        return ToolOutcome(result=run_stale().result), 0
    out = run()
    if out.error:
        return out, 0
    if kind == "malformed_json":
        text = json.dumps(out.result, default=str)
        return ToolOutcome(result=text[: max(1, len(text) // 2)], patch=out.patch), 0
    if kind == "empty":
        empty: Any = [] if isinstance(out.result, list) else {}
        return ToolOutcome(result=empty, patch=out.patch), 0
    if kind == "schema_drift":
        rename = fault.params.get("rename", {})

        def drift(v: Any) -> Any:
            if isinstance(v, dict):
                return {rename.get(k, k): drift(x) for k, x in v.items()}
            if isinstance(v, list):
                return [drift(x) for x in v]
            return v

        return ToolOutcome(result=drift(out.result), patch=out.patch), 0
    return out, 0
