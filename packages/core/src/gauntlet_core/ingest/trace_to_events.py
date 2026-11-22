"""Spans to journal-shaped events (P5-1). `sim_time` carries the real span time (CQ-P2)."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from fnmatch import fnmatchcase
from typing import Any, Literal

from gauntlet_core.schema import Event, Origin

from .semconv import Span, detect_semconv, indexed_messages, session_of, tool_args

__all__ = ["ConvertedConversation", "group_spans", "trace_to_events"]

Semconv = Literal["openinference", "genai", "auto"]
STRUCTURAL = {"AGENT", "CHAIN"}


@dataclass
class ConvertedConversation:
    session_id: str
    events: list[Event]
    unknown_spans: int = 0
    structural_spans: int = 0


def group_spans(spans: Sequence[Span]) -> dict[str, list[Span]]:
    """Conversations by `session.id` (any span of a trace carrying one names the whole trace),
    else by trace id."""
    by_trace: dict[str, str] = {}
    for s in spans:
        sid = session_of(s)
        if sid:
            by_trace[s.trace_id] = sid
    out: dict[str, list[Span]] = defaultdict(list)
    for s in spans:
        out[by_trace.get(s.trace_id, s.trace_id)].append(s)
    return dict(out)


def _when(ns: int) -> datetime:
    return datetime.fromtimestamp(ns / 1e9, tz=UTC)


def _text(v: Any) -> str:
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)


def _kind(span: Span, flavour: str) -> str:
    a = span.attributes
    if flavour == "openinference":
        return str(a.get("openinference.span.kind", "")).upper()
    op = str(a.get("gen_ai.operation.name", ""))
    return {"chat": "LLM", "text_completion": "LLM", "execute_tool": "TOOL"}.get(op, op.upper())


def trace_to_events(
    spans: Sequence[Span],
    *,
    semconv: Semconv = "auto",
    untrusted_tools: Sequence[str] = (),
) -> ConvertedConversation:
    ordered = sorted(spans, key=lambda s: (s.start_ns, s.end_ns, s.span_id))
    session = next((session_of(s) for s in ordered if session_of(s)), None) or (
        ordered[0].trace_id if ordered else ""
    )
    drafts: list[tuple[int, int, str, str, dict[str, Any], Origin | None]] = []
    unknown = structural = 0
    seen_inputs: dict[str, int] = {}  # per trace: how many input messages the last LLM span had
    last_user: str | None = None
    n = 0

    def add(ns: int, kind: str, actor: str, payload: dict[str, Any], origin: Origin | None = None):
        nonlocal n
        n += 1
        drafts.append((ns, n, kind, actor, payload, origin))

    for sp in ordered:
        flavour = semconv if semconv != "auto" else detect_semconv(sp)
        kind = _kind(sp, flavour) if flavour else ""
        a = sp.attributes
        if flavour is None or kind in ("", "RETRIEVER", "EMBEDDING", "RERANKER", "GUARDRAIL"):
            unknown += 1
            add(sp.start_ns, "sim_note", "platform",
                {"note": "unmapped_span", "name": sp.name, "span_kind": kind or None})  # fmt: skip
        elif kind in STRUCTURAL:
            structural += 1
        elif kind == "LLM":
            prefix_in, prefix_out = (
                ("llm.input_messages", "llm.output_messages")
                if flavour == "openinference"
                else ("gen_ai.prompt", "gen_ai.completion")
            )
            msgs = indexed_messages(a, prefix_in, flavour=flavour)
            prev = seen_inputs.get(sp.trace_id, 0)
            fresh = list(msgs[prev:] if len(msgs) >= prev else msgs[-1:])
            last_msg = next((m for m in reversed(msgs) if m.role == "user"), None)
            if last_msg is not None and last_msg not in fresh:
                fresh.append(last_msg)  # a span that carries only the new turn
            seen_inputs[sp.trace_id] = len(msgs)
            for m in fresh:
                if m.role == "user" and m.content and m.content != last_user:
                    last_user = m.content
                    add(sp.start_ns, "user_message", "user", {"text": m.content},
                        Origin(trust="user"))  # fmt: skip
            for m in indexed_messages(a, prefix_out, flavour=flavour):
                if m.content and not m.tool_calls:
                    add(sp.end_ns, "agent_message", "agent", {"text": m.content},
                        Origin(trust="system"))  # fmt: skip
        elif kind == "TOOL":
            name = str(a.get("tool.name") or a.get("gen_ai.tool.name") or sp.name)
            raw = (
                a.get("tool.parameters")
                or a.get("gen_ai.tool.call.arguments")
                or a.get("input.value")
            )
            result = a.get("output.value", a.get("gen_ai.tool.call.result"))
            call_id = f"call_{sp.span_id}"
            call = {"call_id": call_id, "tool": name, "args": tool_args(raw), "via": "trace"}
            add(sp.start_ns, "tool_call", "agent", call)
            untrusted = any(fnmatchcase(name, g) for g in untrusted_tools)
            done = {
                "call_id": call_id,
                "ok": not sp.error,
                "result": None if result is None else _text(result),
                "patch": [],
                "error": "tool error" if sp.error else None,
            }
            trust = "untrusted_external" if untrusted else "system"
            add(sp.end_ns, "tool_result", "tool", done, Origin(trust=trust, source=name))
        else:
            unknown += 1
            add(sp.start_ns, "sim_note", "platform",
                {"note": "unmapped_span", "name": sp.name, "span_kind": kind})  # fmt: skip
    drafts.sort(key=lambda d: (d[0], d[1]))
    events = [
        Event(seq=i + 1, kind=k, actor=actor, sim_time=_when(ns), payload=p, origin=o)  # type: ignore[arg-type]
        for i, (ns, _, k, actor, p, o) in enumerate(drafts)
    ]
    return ConvertedConversation(session, events, unknown, structural)
