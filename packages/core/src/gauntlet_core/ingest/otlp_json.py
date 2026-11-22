"""OTLP/JSON trace documents to `Span`s (P5-1). Pure; the protobuf path in the server turns a
request into this same dict shape first."""

from __future__ import annotations

import base64
from typing import Any

from .semconv import Span

__all__ = ["attr_value", "spans_from_otlp"]


def attr_value(v: dict[str, Any]) -> Any:
    if "stringValue" in v:
        return v["stringValue"]
    if "boolValue" in v:
        return bool(v["boolValue"])
    if "intValue" in v:
        return int(v["intValue"])
    if "doubleValue" in v:
        return float(v["doubleValue"])
    if "arrayValue" in v:
        return [attr_value(x) for x in v["arrayValue"].get("values", [])]
    if "kvlistValue" in v:
        return {
            kv["key"]: attr_value(kv.get("value", {})) for kv in v["kvlistValue"].get("values", [])
        }
    if "bytesValue" in v:
        return v["bytesValue"]
    return None


def _id(raw: str | None, b64: bool) -> str:
    if not raw:
        return ""
    return base64.b64decode(raw).hex() if b64 else raw.lower()


def spans_from_otlp(doc: dict[str, Any], *, b64_ids: bool = False) -> list[Span]:
    """`b64_ids`: ids are base64 (the canonical protobuf JSON mapping) instead of hex."""
    out: list[Span] = []
    for rs in doc.get("resourceSpans", []) or []:
        for ss in rs.get("scopeSpans", []) or []:
            for sp in ss.get("spans", []) or []:
                attrs = {a["key"]: attr_value(a.get("value", {})) for a in sp.get("attributes", [])}
                status = (sp.get("status") or {}).get("code")
                out.append(
                    Span(
                        trace_id=_id(sp.get("traceId"), b64_ids),
                        span_id=_id(sp.get("spanId"), b64_ids),
                        parent_id=_id(sp.get("parentSpanId"), b64_ids) or None,
                        name=str(sp.get("name", "")),
                        start_ns=int(sp.get("startTimeUnixNano", 0)),
                        end_ns=int(sp.get("endTimeUnixNano", 0) or sp.get("startTimeUnixNano", 0)),
                        attributes=attrs,
                        error=status in (2, "STATUS_CODE_ERROR"),
                    )
                )
    return out
