# pyright: reportOptionalMemberAccess=false
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from datetime import UTC, datetime

from gauntlet_core.ingest import group_spans, trace_to_events
from trace_helpers import spans


def shape(conv):
    return [
        (e.kind, e.payload.get("text") or e.payload.get("tool") or e.payload.get("note"))
        for e in conv.events
    ]


def test_openinference_conversation():
    conv = trace_to_events(spans("openinference_support"))
    assert conv.session_id == "sess-1"
    assert shape(conv) == [
        ("user_message", "Hi, where is order ord_1001?"),
        ("tool_call", "lookup_order"),
        ("tool_result", None),
        ("sim_note", "unmapped_span"),
        ("agent_message", "Order ord_1001 has shipped."),
        ("user_message", "Thanks!"),
        ("agent_message", "You are welcome."),
    ]
    assert conv.unknown_spans == 1 and conv.structural_spans == 1
    assert [e.seq for e in conv.events] == list(range(1, 8))
    call = conv.events[1].payload
    assert call["args"] == {"order_id": "ord_1001"} and call["via"] == "trace"
    res = conv.events[2].payload
    assert res["call_id"] == call["call_id"] and res["ok"] is True and "shipped" in res["result"]
    assert conv.events[0].origin.trust == "user" and conv.events[2].origin.trust == "system"


def test_real_time_is_preserved_in_sim_time():
    conv = trace_to_events(spans("openinference_support"))
    first = conv.events[0].sim_time
    assert first.tzinfo is not None and first.year >= 2026
    assert first == datetime.fromtimestamp((1_780_000_000_000_000_000 + 10_000_000) / 1e9, tz=UTC)
    assert [e.sim_time for e in conv.events] == sorted(e.sim_time for e in conv.events)


def test_genai_conversation():
    conv = trace_to_events(spans("genai_support"))
    assert conv.session_id == "sess-2"
    assert shape(conv) == [
        ("user_message", "Cancel order ord_2002"),
        ("tool_call", "cancel_order"),
        ("tool_result", None),
        ("agent_message", "Done, it is cancelled."),
    ]


def test_untrusted_tool_origin_by_glob():
    conv = trace_to_events(spans("openinference_support"), untrusted_tools=["lookup_*"])
    result = next(e for e in conv.events if e.kind == "tool_result")
    assert result.origin.trust == "untrusted_external" and result.origin.source == "lookup_order"


def test_unknown_spans_become_notes_never_dropped():
    from gauntlet_core.ingest import Span

    odd = Span("t", "x", None, "mystery", 1, 2, {"foo": "bar"})
    conv = trace_to_events([odd])
    assert conv.unknown_spans == 1 and conv.events[0].kind == "sim_note"
    assert conv.events[0].payload == {"note": "unmapped_span", "name": "mystery", "span_kind": None}


def test_grouping_by_session_then_trace():
    all_spans = spans("openinference_support") + spans("genai_support")
    groups = group_spans(all_spans)
    assert set(groups) == {"sess-1", "sess-2"}
    from gauntlet_core.ingest import Span

    lone = Span("zzz", "1", None, "a", 1, 2, {})
    assert "zzz" in group_spans([lone])


def test_tool_error_marks_result_not_ok():
    from gauntlet_core.ingest import Span

    s = Span(
        "t",
        "x",
        None,
        "t",
        1,
        2,
        {"openinference.span.kind": "TOOL", "tool.name": "refund", "input.value": "x"},
        error=True,
    )
    conv = trace_to_events([s])
    assert conv.events[1].payload["ok"] is False and conv.events[1].payload["error"]
