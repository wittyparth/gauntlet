"""Builds the hand-made OTLP/JSON fixtures in this directory: `uv run python build.py`.
Everything here is fictional."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
T0 = 1_780_000_000_000_000_000  # an arbitrary fixed instant, nanoseconds


def val(v: Any) -> dict[str, Any]:
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, int):
        return {"intValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    return {"stringValue": str(v)}


def span(trace: str, sid: str, name: str, start: int, end: int, attrs: dict[str, Any],
         parent: str = "", error: bool = False) -> dict[str, Any]:  # fmt: skip
    out = {
        "traceId": trace,
        "spanId": sid,
        "parentSpanId": parent,
        "name": name,
        "startTimeUnixNano": str(T0 + start * 1_000_000),
        "endTimeUnixNano": str(T0 + end * 1_000_000),
        "attributes": [{"key": k, "value": val(v)} for k, v in attrs.items()],
    }
    if error:
        out["status"] = {"code": 2, "message": "boom"}
    return out


def doc(spans: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "resourceSpans": [
            {
                "resource": {"attributes": [{"key": "service.name", "value": val("support-bot")}]},
                "scopeSpans": [{"scope": {"name": "fixture"}, "spans": spans}],
            }
        ]
    }


def oi_llm(i: dict[int, tuple[str, str]], o: tuple[str, str] | None, calls=()):
    a: dict[str, Any] = {"openinference.span.kind": "LLM"}
    for n, (role, content) in i.items():
        a[f"llm.input_messages.{n}.message.role"] = role
        a[f"llm.input_messages.{n}.message.content"] = content
    if o is not None:
        a["llm.output_messages.0.message.role"] = o[0]
        a["llm.output_messages.0.message.content"] = o[1]
    for k, (name, args) in enumerate(calls):
        base = f"llm.output_messages.0.message.tool_calls.{k}.tool_call.function"
        a[f"{base}.name"], a[f"{base}.arguments"] = name, args
    return a


def openinference() -> dict[str, Any]:
    t = "a" * 32
    sysm = (0, ("system", "You are a support agent."))
    user1 = (1, ("user", "Hi, where is order ord_1001?"))
    return doc(
        [
            span(t, "s0", "agent", 0, 400, {"openinference.span.kind": "AGENT", "session.id": "sess-1"}),
            span(t, "s1", "llm", 10, 20, oi_llm({0: sysm[1], 1: user1[1]}, None,
                 calls=[("lookup_order", '{"order_id": "ord_1001"}')]), "s0"),
            span(t, "s2", "lookup_order", 30, 40, {
                "openinference.span.kind": "TOOL", "tool.name": "lookup_order",
                "tool.parameters": '{"order_id": "ord_1001"}',
                "output.value": '{"id": "ord_1001", "status": "shipped"}'}, "s0"),
            span(t, "s3", "retrieve", 42, 48, {"openinference.span.kind": "RETRIEVER"}, "s0"),
            span(t, "s4", "llm", 50, 60, oi_llm(
                {0: sysm[1], 1: user1[1], 2: ("assistant", ""), 3: ("tool", "shipped")},
                ("assistant", "Order ord_1001 has shipped.")), "s0"),
            span(t, "s5", "llm", 300, 310, oi_llm(
                {0: sysm[1], 1: user1[1], 2: ("assistant", ""), 3: ("tool", "shipped"),
                 4: ("assistant", "Order ord_1001 has shipped."), 5: ("user", "Thanks!")},
                ("assistant", "You are welcome.")), "s0"),
        ]
    )  # fmt: skip


def genai() -> dict[str, Any]:
    t = "b" * 32
    chat1 = {
        "gen_ai.operation.name": "chat", "gen_ai.conversation.id": "sess-2",
        "gen_ai.prompt.0.role": "user", "gen_ai.prompt.0.content": "Cancel order ord_2002",
        "gen_ai.completion.0.role": "assistant", "gen_ai.completion.0.content": "",
    }  # fmt: skip
    tool = {
        "gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "cancel_order",
        "gen_ai.tool.call.arguments": '{"order_id": "ord_2002"}',
        "gen_ai.tool.call.result": "cancelled",
    }  # fmt: skip
    chat2 = {
        "gen_ai.operation.name": "chat",
        "gen_ai.prompt.0.role": "user", "gen_ai.prompt.0.content": "Cancel order ord_2002",
        "gen_ai.prompt.1.role": "tool", "gen_ai.prompt.1.content": "cancelled",
        "gen_ai.completion.0.role": "assistant", "gen_ai.completion.0.content": "Done, it is cancelled.",
    }  # fmt: skip
    return doc(
        [
            span(t, "g1", "chat", 0, 10, chat1),
            span(t, "g2", "execute_tool cancel_order", 12, 20, tool),
            span(t, "g3", "chat", 22, 30, chat2),
        ]
    )


EMAIL, CARD, KEY, PHONE = "jane.doe@example.com", "4242 4242 4242 4242", "AKIAIOSFODNN7EXAMPLE", "415-555-0132"


def planted() -> dict[str, Any]:
    t = "c" * 32
    return doc(
        [
            span(t, "p1", "llm", 0, 10, {
                "openinference.span.kind": "LLM", "session.id": "sess-pii",
                **oi_llm({0: ("user", f"My email is {EMAIL} and my card is {CARD}, call {PHONE}")},
                         ("assistant", f"Thanks, I will email {EMAIL}."),),
                "api_key": KEY, "http.headers.authorization": f"Bearer {KEY}"}),
            span(t, "p2", "send_email", 12, 20, {
                "openinference.span.kind": "TOOL", "tool.name": "send_email",
                "tool.parameters": json.dumps({"to": EMAIL, "authorization": KEY,
                                               "note": f"key {KEY}"}),
                "output.value": f"sent to {EMAIL}"}),
        ]
    )  # fmt: skip


if __name__ == "__main__":
    for name, d in (("openinference_support", openinference()), ("genai_support", genai()),
                    ("planted_pii", planted())):  # fmt: skip
        (HERE / f"{name}.json").write_text(json.dumps(d, indent=1) + "\n")
