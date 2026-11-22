"""Decode an OTLP/HTTP trace export request (protobuf or JSON) into spans (P5-1)."""

from __future__ import annotations

import json
from typing import Any

from gauntlet_core.ingest import Span, spans_from_otlp
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)

from ..errors import ApiError

__all__ = ["decode_request", "encode_response", "is_protobuf"]


def is_protobuf(content_type: str | None) -> bool:
    return "protobuf" in (content_type or "").lower()


def decode_request(body: bytes, content_type: str | None) -> list[Span]:
    try:
        if is_protobuf(content_type):
            req = ExportTraceServiceRequest()
            req.ParseFromString(body)
            doc: dict[str, Any] = MessageToDict(req)
            return spans_from_otlp(doc, b64_ids=True)
        doc = json.loads(body or b"{}")
    except (DecodeError, ValueError) as e:
        raise ApiError(
            400, "invalid_otlp", f"cannot decode the trace export: {type(e).__name__}"
        ) from e
    if not isinstance(doc, dict):
        raise ApiError(400, "invalid_otlp", "the export must be a JSON object")
    return spans_from_otlp(doc)


def encode_response(rejected: int) -> bytes:
    resp = ExportTraceServiceResponse()
    if rejected:
        resp.partial_success.rejected_spans = rejected
    return resp.SerializeToString()
