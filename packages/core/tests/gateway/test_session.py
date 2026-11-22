# pyright: reportOptionalMemberAccess=false
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from gauntlet_core.gateway import Guard, MemorySink
from gauntlet_core.gateway.session import MAX_PREFIX
from gw_helpers import REFUND_CAP, policy, rule, tool


async def test_origin_tagging():
    g = Guard(policy(REFUND_CAP), origin_rules=["web_*"], tool_risk={"issue_refund": "financial"})
    s = g.session("s1", user_id="u1")
    await s.record_user_message("hello")
    await s.record_agent_message("hi")
    await s.record_tool_result("c1", "lookup", {"x": 1})
    await s.record_tool_result("c2", "web_fetch", "page")  # glob rule
    await s.record_tool_result("c3", "lookup", "page", untrusted=True, source="crm")
    await s.record_tool_result("c4", "web_fetch", "page", untrusted=False)  # explicit wins
    trust = [(e.kind, e.origin.trust if e.origin else None) for e in s.events]
    assert trust == [
        ("user_message", "user"),
        ("agent_message", "system"),
        ("tool_result", "system"),
        ("tool_result", "untrusted_external"),
        ("tool_result", "untrusted_external"),
        ("tool_result", "system"),
    ]
    assert s.events[4].origin.source == "crm"
    assert s.user_id == "u1"


async def test_wrapped_untrusted_output_is_tagged():
    g = Guard(policy())
    s = g.session()

    @g.tool(untrusted_output=True)
    def fetch() -> str:
        return "content"

    await fetch(session=s)
    assert s.events[-1].origin.trust == "untrusted_external"
    assert g.is_untrusted_tool("fetch")


async def test_tool_call_is_appended_after_the_decision_and_seqs_are_dense():
    sink = MemorySink()
    g = Guard(policy(REFUND_CAP), sink=sink)
    s = g.session()
    await s.record_user_message("refund me")
    d1 = await s.check_tool_call("lookup_order", {"order_id": "o1"}, call_id="c1")
    await s.record_tool_result("c1", "lookup_order", {"total": 5})
    d2 = await s.check_tool_call("issue_refund", {"amount_cents": 20000}, call_id="c2")
    d3 = await s.check_tool_call("issue_refund", {"amount_cents": 5}, call_id="c3")
    assert (d1.action, d2.action, d3.action) == ("allow", "block", "allow")
    kinds = [e.kind for e in s.events]
    # the blocked call never went ahead, so it is not part of the history
    assert kinds == ["user_message", "tool_call", "tool_result", "tool_call"]
    assert [e.seq for e in s.events] == [1, 2, 3, 4]
    assert [e.payload["call_id"] for e in s.events if e.kind == "tool_call"] == ["c1", "c3"]
    assert len(sink.records) == 3


async def test_history_is_visible_to_rules():
    one_coupon = rule("one-coupon", tool("apply_coupon", count={"min": 2}), message="one only")
    g = Guard(policy(one_coupon))
    s = g.session()
    assert (await s.check_tool_call("apply_coupon", {"code": "A"})).action == "allow"
    second = await s.check_tool_call("apply_coupon", {"code": "B"})
    assert second.action == "block" and second.rule_id == "one-coupon"
    assert (await g.session().check_tool_call("apply_coupon", {"code": "B"})).action == "allow"


async def test_prefix_cap_keeps_first_user_message():
    g = Guard(policy())
    s = g.session()
    await s.record_user_message("first")
    for i in range(MAX_PREFIX + 50):
        await s.record_agent_message(f"m{i}")
    assert len(s.events) == MAX_PREFIX
    assert s.events[0].payload["text"] == "first"
    assert s.events[-1].payload["text"] == f"m{MAX_PREFIX + 49}"
    seqs = [e.seq for e in s.events]
    assert seqs == sorted(seqs)


async def test_decision_records_carry_the_episode_id_only_when_given():
    sink = MemorySink()
    g = Guard(policy(REFUND_CAP), sink=sink)
    plain = g.session("s1")
    await plain.check_tool_call("issue_refund", {"amount_cents": 20000}, call_id="c1")
    sim = g.session("ep:ep_1", episode_id="ep_1")
    await sim.check_tool_call("issue_refund", {"amount_cents": 20000}, call_id="c2")
    assert [r.episode_id for r in sink.records] == [None, "ep_1"]
