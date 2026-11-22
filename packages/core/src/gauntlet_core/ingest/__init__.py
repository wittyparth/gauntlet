"""Production trace ingestion: spans to events, with redaction (P5-1)."""

from .otlp_json import spans_from_otlp
from .redact import SECRET_KEYS, RedactionConfig, Redactor
from .semconv import SEMCONV_VERSIONS, Message, Span, detect_semconv, session_of
from .trace_to_events import ConvertedConversation, group_spans, trace_to_events

__all__ = [
    "SECRET_KEYS",
    "SEMCONV_VERSIONS",
    "ConvertedConversation",
    "Message",
    "RedactionConfig",
    "Redactor",
    "Span",
    "detect_semconv",
    "group_spans",
    "session_of",
    "spans_from_otlp",
    "trace_to_events",
]
