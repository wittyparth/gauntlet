"""Seed records generated from OpenAPI response schemas. No network, no model: a fixed word
list and a seeded `random.Random`, so the same spec and `rng_seed` give the same records."""

from __future__ import annotations

import random
import uuid
from typing import Any

from gauntlet_core.schema import Json

WORDS = ["amber", "birch", "cobalt", "delta", "ember", "fjord", "garnet", "harbor", "indigo"]
NAMES = ["Avery Stone", "Blake Moreno", "Casey Lindqvist", "Devon Okoye", "Emery Fox"]
TITLES = ["Quarterly summary", "Welcome guide", "Release notes", "Annual plan", "Field report"]
DESCRIPTIONS = [
    "A short sample description.",
    "Created for testing; not real data.",
    "Placeholder text for a generated record.",
]
MAX_DEPTH = 2


def flatten(schema: Any) -> Json:
    """Collapse `allOf`, `oneOf`/`anyOf` (first branch) and OpenAPI 3.1 type lists."""
    if not isinstance(schema, dict):
        return {}
    out: Json = {k: v for k, v in schema.items() if k not in ("allOf", "oneOf", "anyOf")}
    for part in schema.get("allOf", []):
        sub = flatten(part)
        props = {**out.get("properties", {}), **sub.get("properties", {})}
        required = [*out.get("required", []), *sub.get("required", [])]
        out = {**sub, **out, "properties": props, "required": required}
        if not props:
            out.pop("properties")
    for key in ("oneOf", "anyOf"):
        options = [
            o for o in schema.get(key, []) if isinstance(o, dict) and o.get("type") != "null"
        ]
        if options:
            out = {**flatten(options[0]), **out}
    t = out.get("type")
    if isinstance(t, list):
        non_null = [x for x in t if x != "null"]
        out["type"] = non_null[0] if non_null else "string"
    return out


def stem(collection: str) -> str:
    """The id stem, matching the crud `create` handler (`orders` -> `order`)."""
    return collection[:-1] if collection.endswith("s") else collection


def _string(name: str, schema: Json, n: int, rng: random.Random) -> str:
    fmt = schema.get("format")
    if fmt == "email":
        return f"user{n}@example.test"
    if fmt in ("date-time", "date"):
        month, day = rng.randrange(1, 13), rng.randrange(1, 28)
        stamp = f"2026-{month:02d}-{day:02d}"
        return stamp if fmt == "date" else f"{stamp}T{rng.randrange(24):02d}:00:00Z"
    if fmt == "uuid":
        return str(uuid.UUID(int=rng.getrandbits(128), version=4))
    if fmt in ("uri", "url"):
        return f"https://example.test/{n}"
    low = name.lower()
    if "email" in low:
        return f"user{n}@example.test"
    if "name" in low:
        return NAMES[(n - 1) % len(NAMES)]
    if "title" in low:
        return TITLES[(n - 1) % len(TITLES)]
    if "description" in low or "note" in low or "comment" in low:
        return DESCRIPTIONS[(n - 1) % len(DESCRIPTIONS)]
    return f"{rng.choice(WORDS)}-{n}"


def value(name: str, schema: Any, n: int, rng: random.Random, depth: int = 0) -> Any:
    s = flatten(schema)
    if s.get("enum"):
        return s["enum"][(n - 1) % len(s["enum"])]
    kind = s.get("type") or ("object" if "properties" in s else "string")
    if kind == "string":
        return _string(name, s, n, rng)
    if kind == "integer":
        lo, hi = int(s.get("minimum", 0)), int(s.get("maximum", 1000))
        return rng.randint(lo, max(lo, hi))
    if kind == "number":
        lo, hi = float(s.get("minimum", 0)), float(s.get("maximum", 1000))
        return round(rng.uniform(lo, max(lo, hi)), 2)
    if kind == "boolean":
        return rng.random() < 0.5
    if depth >= MAX_DEPTH:
        return [] if kind == "array" else {}
    if kind == "array":
        item = s.get("items", {})
        return [value(name, item, n + i, rng, depth + 1) for i in range(2)]
    return {k: value(k, sub, n, rng, depth + 1) for k, sub in (s.get("properties") or {}).items()}


def record(coll: str, n: int, schema: Any, rng: random.Random) -> Json:
    """One seed record: `id` is always `{stem}_{n}`, other fields come from the schema."""
    s = flatten(schema)
    rec: Json = {"id": f"{stem(coll)}_{n}"}
    for k, sub in (s.get("properties") or {}).items():
        if k != "id":
            rec[k] = value(k, sub, n, rng, 1)
    return rec


def item_schema(response_schema: Any) -> Json:
    """The record schema inside a list response: the array items, or the first array-valued
    property of a wrapper object (`{"items": [...]}`, `{"data": [...]}`)."""
    s = flatten(response_schema)
    if s.get("type") == "array":
        return flatten(s.get("items", {}))
    for sub in (s.get("properties") or {}).values():
        sub = flatten(sub)
        if sub.get("type") == "array":
            return flatten(sub.get("items", {}))
    return s
