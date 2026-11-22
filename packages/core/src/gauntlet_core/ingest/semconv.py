"""Span model and the two semantic conventions we read (P5-1).

OpenInference (https://github.com/Arize-ai/openinference, semantic conventions as of the
`openinference-semantic-conventions` 0.1.x series): `openinference.span.kind` in LLM, TOOL,
AGENT, CHAIN, RETRIEVER, ...; flattened `llm.input_messages.N.message.role|content`,
`llm.output_messages.N.message.content` and `...tool_calls.M.tool_call.function.name|arguments`;
`tool.name`, `tool.parameters`, `input.value`, `output.value`, `session.id`.

OTel GenAI (`gen_ai.*`, development status): `gen_ai.operation.name` (`chat`, `execute_tool`),
`gen_ai.prompt.N.role|content` and `gen_ai.completion.N.role|content` (the attribute form that
instrumentations still emit), `gen_ai.tool.name`, `gen_ai.tool.call.arguments|result`.
The span-event form (`gen_ai.user.message`, ...) is not read: such spans fall back to notes.
**Verify both specs' current attribute names before relying on a new instrumentation version.**
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "SEMCONV_VERSIONS",
    "Message",
    "Span",
    "detect_semconv",
    "indexed_messages",
    "session_of",
    "tool_args",
]

SEMCONV_VERSIONS = {"openinference": "0.1.x", "genai": "development"}


@dataclass
class Span:
    trace_id: str
    span_id: str
    parent_id: str | None
    name: str
    start_ns: int
    end_ns: int
    attributes: dict[str, Any] = field(default_factory=dict)
    error: bool = False


@dataclass(frozen=True)
class Message:
    role: str
    content: str
    tool_calls: tuple[tuple[str, str], ...] = ()  # (name, arguments json text)


def detect_semconv(span: Span) -> str | None:
    a = span.attributes
    if "openinference.span.kind" in a:
        return "openinference"
    if any(k.startswith("gen_ai.") for k in a):
        return "genai"
    return None


def session_of(span: Span) -> str | None:
    v = span.attributes.get("session.id") or span.attributes.get("gen_ai.conversation.id")
    return str(v) if v else None


_IDX = re.compile(r"^(\d+)\.(.+)$")


def indexed_messages(attrs: dict[str, Any], prefix: str, *, flavour: str) -> list[Message]:
    """Messages flattened as `<prefix>.N.<...>`. OpenInference nests under `.message.`;
    GenAI uses `<prefix>.N.role|content`."""
    grouped: dict[int, dict[str, Any]] = {}
    for key, value in attrs.items():
        if not key.startswith(prefix + "."):
            continue
        m = _IDX.match(key[len(prefix) + 1 :])
        if m:
            grouped.setdefault(int(m.group(1)), {})[m.group(2)] = value
    out: list[Message] = []
    for _, f in sorted(grouped.items()):
        base = "message." if flavour == "openinference" else ""
        calls: dict[int, dict[str, str]] = {}
        for k, v in f.items():
            m = re.match(
                rf"^{re.escape(base)}tool_calls\.(\d+)\.tool_call\.function\.(name|arguments)$", k
            )
            if m:
                calls.setdefault(int(m.group(1)), {})[m.group(2)] = str(v)
        out.append(
            Message(
                role=str(f.get(f"{base}role", "")),
                content=str(f.get(f"{base}content", "") or ""),
                tool_calls=tuple(
                    (c.get("name", ""), c.get("arguments", "{}")) for _, c in sorted(calls.items())
                ),
            )
        )
    return out


def tool_args(raw: Any) -> Any:
    """Tool arguments as an object when they are JSON text, else the text."""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return {"input": raw}
    return raw if raw is not None else {}
