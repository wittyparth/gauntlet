"""OpenAPI 3.x import: operations become `ToolSpec`s, response schemas become seed data.

Collections follow REST shape (`/things`, `/things/{id}`) and get `crud` handlers; every other
operation becomes an `llm_sim` handler with a warning. Only local `#/` refs are resolved."""

from __future__ import annotations

import random
import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from gauntlet_core.schema import (
    CrudHandler,
    Json,
    LLMSimHandler,
    Risk,
    ToolSpec,
    WorldSpec,
)

from .openapi_seed import flatten, item_schema, record

__all__ = ["OpenAPIImport", "import_openapi"]

MAX_REF_DEPTH = 6
METHODS = ("get", "post", "put", "patch", "delete")
NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
PAGINATION = {"limit", "offset", "page", "page_size", "per_page", "cursor", "sort", "order"}
_FINANCIAL = re.compile(r"refund|pay|charge|transfer|payout|invoice|billing", re.I)
_EXTERNAL = re.compile(r"email|sms|send|notify|message|webhook", re.I)
_DESTRUCTIVE = re.compile(r"delete|destroy|purge|drop|cancel|revoke", re.I)
_UNTRUSTED = re.compile(
    r"search|fetch|browse|web|inbox|mail|message|comment|review|issue|document|file|attachment",
    re.I,
)
_PREFIX = re.compile(r"^(v\d+|api)$", re.I)


@dataclass(frozen=True)
class OpenAPIImport:
    tools: list[ToolSpec]
    seed: dict[str, list[Json]]
    warnings: list[str] = field(default_factory=list)

    def to_world(self, world_id: str, clock_start: datetime) -> WorldSpec:
        return WorldSpec(id=world_id, tools=self.tools, seed=self.seed, clock_start=clock_start)


class _Refs:
    def __init__(self, doc: Json, warnings: list[str]) -> None:
        self.doc, self.warnings = doc, warnings

    def _warn(self, msg: str) -> None:
        if msg not in self.warnings:
            self.warnings.append(msg)

    def _target(self, ref: str) -> Any:
        node: Any = self.doc
        for part in ref[2:].split("/"):
            key = urllib.parse.unquote(part).replace("~1", "/").replace("~0", "~")
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                return None
        return node

    def resolve(self, node: Any, depth: int = 0) -> Any:
        if isinstance(node, list):
            return [self.resolve(x, depth) for x in node]
        if not isinstance(node, dict):
            return node
        ref = node.get("$ref")
        if isinstance(ref, str):
            if not ref.startswith("#/"):
                self._warn(f"external $ref {ref!r} not resolved; treated as an empty schema")
                return {}
            if depth >= MAX_REF_DEPTH:
                self._warn(f"$ref {ref!r} exceeds depth {MAX_REF_DEPTH}; treated as empty")
                return {}
            target = self._target(ref)
            if target is None:
                self._warn(f"$ref {ref!r} not found; treated as an empty schema")
                return {}
            return self.resolve(target, depth + 1)
        return {k: self.resolve(v, depth) for k, v in node.items()}


_SCHEMA_MAPS = ("properties", "patternProperties", "$defs", "definitions")
_SCHEMA_LISTS = ("allOf", "anyOf", "oneOf", "prefixItems")
_SCHEMA_ONE = ("items", "additionalProperties", "not", "if", "then", "else")
_TYPES = {"string", "integer", "number", "boolean", "object", "array", "null"}


def _clean(schema: Any) -> Any:
    """Drop OpenAPI 3.0 leftovers that are not valid JSON Schema (boolean `exclusiveMinimum`,
    non-list `required`, unknown `type`)."""
    if not isinstance(schema, dict):
        return schema
    out: Json = {}
    for k, v in schema.items():
        if k in _SCHEMA_MAPS and isinstance(v, dict):
            out[k] = {n: _clean(s) for n, s in v.items()}
        elif k in _SCHEMA_LISTS and isinstance(v, list):
            out[k] = [_clean(s) for s in v]
        elif k in _SCHEMA_ONE:
            out[k] = _clean(v)
        elif k == "required":
            if isinstance(v, list) and all(isinstance(x, str) for x in v):
                out[k] = list(dict.fromkeys(v))
        elif k in ("exclusiveMinimum", "exclusiveMaximum") and isinstance(v, bool):
            continue
        elif k == "type":
            ok = v in _TYPES or (isinstance(v, list) and v and all(x in _TYPES for x in v))
            if ok:
                out[k] = v
        else:
            out[k] = v
    return out


def _snake(text: str) -> str:
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text).lower()
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9_-]", "_", s)).strip("_-")


def _unique(name: str, taken: set[str]) -> str:
    name = (name or "tool")[:60]
    out, i = name, 2
    while out in taken:
        out, i = f"{name}_{i}", i + 1
    taken.add(out)
    return out


def _load(doc: dict[str, Any] | str | Path) -> Json:
    if isinstance(doc, Path):
        doc = doc.read_text()
    elif isinstance(doc, str):
        head = doc.lstrip()
        if "\n" not in doc and not head.startswith("{") and len(doc) < 4096 and Path(doc).is_file():
            doc = Path(doc).read_text()
    data = yaml.safe_load(doc) if isinstance(doc, str) else doc
    if not isinstance(data, dict):
        raise ValueError("OpenAPI document must be a JSON or YAML object")
    if "swagger" in data:
        raise ValueError("Swagger 2.0 is not supported; convert the spec to OpenAPI 3.x first")
    if not str(data.get("openapi", "")).startswith("3."):
        raise ValueError("not an OpenAPI 3.x document (missing `openapi: 3.x`)")
    if not isinstance(data.get("paths"), dict) or not data["paths"]:
        raise ValueError("OpenAPI document has no `paths`")
    return data


def _shape(path: str) -> tuple[str, str | None, str | None]:
    """(kind, collection, key_arg); kind is "collection", "item" or "other"."""
    segs = [s for s in path.strip("/").split("/") if s]
    while len(segs) > 1 and _PREFIX.match(segs[0]):
        segs = segs[1:]
    param = re.compile(r"^\{(.+)\}$")
    if len(segs) == 1 and not param.match(segs[0]):
        return "collection", segs[0], None
    if len(segs) == 2 and not param.match(segs[0]) and (m := param.match(segs[1])):
        return "item", segs[0], m.group(1)
    return "other", None, None


def _params(item: Json, op: Json, refs: _Refs) -> list[Json]:
    merged: dict[tuple[str, str], Json] = {}
    for p in [*item.get("parameters", []), *op.get("parameters", [])]:
        p = refs.resolve(p)
        if isinstance(p, dict) and p.get("name") and p.get("in") in ("path", "query"):
            merged[(p["in"], p["name"])] = p
    return list(merged.values())


def _json_body(op: Json, refs: _Refs) -> tuple[Json | None, bool, bool]:
    """(schema, required, non_json) of the request body."""
    body = refs.resolve(op.get("requestBody") or {})
    content = body.get("content") or {}
    if not content:
        return None, False, False
    for mime, spec in content.items():
        if mime == "application/json" or mime.endswith("+json"):
            return flatten(spec.get("schema", {})), bool(body.get("required")), False
    return None, False, True


def _input_schema(params: list[Json], body: Json | None, body_required: bool, key: str | None):
    props: Json = {}
    required: list[str] = []
    for p in params:
        sub = flatten(p.get("schema", {})) or {"type": "string"}
        if p["name"] == key:
            sub = {"type": "string", "description": "Identifier such as thing_1."}
        if p.get("description") and "description" not in sub:
            sub = {**sub, "description": p["description"]}
        props[p["name"]] = sub
        if p.get("required") or p["in"] == "path":
            required.append(p["name"])
    if body is not None:
        if body.get("type", "object") == "object" and body.get("properties"):
            props.update(body["properties"])
            required += list(body.get("required", []))
        else:
            props["body"] = body
            if body_required:
                required.append("body")
    schema: Json = {"type": "object", "properties": props}
    if required:
        schema["required"] = list(dict.fromkeys(required))
    return _clean(schema)


def _risk(name: str, path: str, method: str) -> Risk:
    text = f"{name} {path}"
    if _FINANCIAL.search(text):
        return "financial"
    if _EXTERNAL.search(text):
        return "external_comm"
    if method == "delete" or _DESTRUCTIVE.search(name):
        return "destructive"
    return "read" if method == "get" else "write"


def _response_schema(op: Json, refs: _Refs) -> Json:
    for code in ("200", "201", "default"):
        resp = refs.resolve((op.get("responses") or {}).get(code) or {})
        for mime, spec in (resp.get("content") or {}).items():
            if mime == "application/json" or mime.endswith("+json"):
                return spec.get("schema") or {}
    return {}


def import_openapi(
    doc: dict[str, Any] | str | Path,
    *,
    seed_per_collection: int = 8,
    rng_seed: int = 0,
    max_tools: int = 40,
) -> OpenAPIImport:
    data = _load(doc)
    warnings: list[str] = []
    refs = _Refs(data, warnings)
    taken: set[str] = set()
    tools: list[ToolSpec] = []
    schemas: dict[str, Json] = {}
    collections: list[str] = []
    for path, item in data["paths"].items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method not in METHODS or not isinstance(op, dict):
                continue
            if len(tools) >= max_tools:
                msg = f"stopped at max_tools={max_tools}; later operations skipped"
                if msg not in warnings:
                    warnings.append(msg)
                continue
            kind, coll, key = _shape(path)
            params = _params(item, op, refs)
            body, body_required, non_json = _json_body(op, refs)
            slug = "_".join(_snake(re.sub(r"[{}]", "", s)) for s in path.strip("/").split("/"))
            base = _snake(str(op["operationId"])) if op.get("operationId") else f"{method}_{slug}"
            name = _unique(base if NAME_RE.match(base) else f"{method}_{slug}", taken)
            handler: Any = None
            if not non_json and kind == "collection" and method == "get":
                skip = PAGINATION
                filters = [
                    p["name"] for p in params if p["in"] == "query" and p["name"] not in skip
                ]
                handler = CrudHandler(collection=coll or "", op="list", filter_args=filters)
            elif not non_json and kind == "collection" and method == "post":
                handler = CrudHandler(collection=coll or "", op="create")
            elif not non_json and kind == "item" and method == "get":
                handler = CrudHandler(collection=coll or "", op="get", key_arg=key)
            elif not non_json and kind == "item" and method in ("put", "patch"):
                handler = CrudHandler(collection=coll or "", op="update", key_arg=key)
            elif not non_json and kind == "item" and method == "delete":
                handler = CrudHandler(collection=coll or "", op="delete", key_arg=key)
            if handler is None:
                why = "non-JSON body" if non_json else "not a plain collection operation"
                warnings.append(f"{method.upper()} {path} ({name}): {why}; simulated by an LLM")
                text = f"{op.get('summary', '')}\n{op.get('description', '')}".strip()
                handler = LLMSimHandler(
                    instructions=(text or f"Simulate {method.upper()} {path}")[:500]
                )
            elif handler.op in ("list", "get") and coll:
                if coll not in schemas:
                    collections.append(coll)
                resp = _response_schema(op, refs)
                cand = item_schema(resp) if handler.op == "list" else flatten(resp)
                if cand.get("properties") or coll not in schemas:
                    schemas[coll] = cand
            untrusted = False
            ext = op.get("x-gauntlet-untrusted")
            if ext is not None:
                untrusted = bool(ext)
            elif method == "get" and _UNTRUSTED.search(path):
                untrusted = True
                warnings.append(f"{name}: marked untrusted by heuristic, review")
            summary = " ".join(x for x in (op.get("summary"), op.get("description")) if x)
            tools.append(
                ToolSpec(
                    name=name,
                    description=summary[:500] or f"{method.upper()} {path}",
                    input_schema=_input_schema(params, body, body_required, key),
                    risk=_risk(name, path, method),
                    handler=handler,
                    untrusted_output=untrusted,
                )
            )
    rng = random.Random(rng_seed)
    seed: dict[str, list[Json]] = {}
    for coll in sorted(collections):
        schema = schemas[coll]
        if not schema.get("properties"):
            warnings.append(f"collection {coll!r}: no response schema, seed records only have ids")
        seed[coll] = [record(coll, n, schema, rng) for n in range(1, seed_per_collection + 1)]
    return OpenAPIImport(tools=tools, seed=seed, warnings=warnings)
