import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pytest
from gauntlet_core.gateway import Guard, MemorySink, NoActiveSession, PolicyBlocked
from gw_helpers import REFUND_CAP, policy, rule, tool


def refund_tools(guard):
    calls = []

    @guard.tool(risk="financial")
    def issue_refund(order_id: str, amount_cents: int) -> dict:
        calls.append(amount_cents)
        return {"ok": True}

    @guard.tool(name="lookup")
    async def lookup_order(order_id: str) -> dict:
        calls.append(order_id)
        return {"order": order_id}

    return issue_refund, lookup_order, calls


async def test_sync_and_async_tools_with_contextvar_session():
    g = Guard(policy(REFUND_CAP))
    refund, lookup, calls = refund_tools(g)
    s = g.session()
    async with s.active():
        assert await lookup("o1") == {"order": "o1"}
        assert await refund("o1", amount_cents=500) == {"ok": True}
    assert calls == ["o1", 500]
    assert g.tool_risk["issue_refund"] == "financial"
    assert [e.kind for e in s.events] == ["tool_call", "tool_result", "tool_call", "tool_result"]
    assert s.events[0].payload["tool"] == "lookup"


async def test_block_raises_by_default():
    g = Guard(policy(REFUND_CAP))
    refund, _, calls = refund_tools(g)
    async with g.session().active():
        with pytest.raises(PolicyBlocked) as e:
            await refund("o1", 20000)
    assert e.value.decision.rule_id == "refund-cap" and "10000" in str(e.value)
    assert calls == []  # the tool never ran


async def test_block_can_return_an_error_result_instead():
    g = Guard(policy(REFUND_CAP), on_block="return")
    refund, _, calls = refund_tools(g)
    out = await refund("o1", 20000, session=g.session())
    assert out == {
        "error": "blocked_by_policy",
        "message": "Refunds over 10000 cents are not allowed.",
    }
    assert calls == []


async def test_explicit_session_and_missing_session():
    g = Guard(policy())
    refund, _, _ = refund_tools(g)
    assert await refund("o", 1, session=g.session()) == {"ok": True}
    with pytest.raises(NoActiveSession):
        await refund("o", 1)


async def test_session_scope_ends_with_the_context():
    g = Guard(policy())
    refund, _, _ = refund_tools(g)
    async with g.session().active():
        pass
    with pytest.raises(NoActiveSession):
        await refund("o", 1)


async def test_redact_rewrites_the_arguments_the_tool_receives():
    seen = []
    redact = rule("pin", tool("send", args={"body": {"regex": r"\d{4}"}}), action="redact")
    g = Guard(policy(redact))

    @g.tool()
    def send(to: str, body: str) -> str:
        seen.append(body)
        return "sent"

    s = g.session()
    assert await send("a@b.c", "pin is 1234 ok", session=s) == "sent"
    assert seen == ["pin is [REDACTED:pin] ok"]
    assert s.events[0].payload["args"]["body"] == "pin is [REDACTED:pin] ok"


async def test_redact_on_output():
    r = rule("pin", {"type": "output", "matcher": {"regex": r"\d{4}"}}, action="redact")
    g = Guard(policy(r))
    d = await g.session().check_output("code 9876 here")
    assert d.action == "redact" and d.modified == {"text": "code [REDACTED:pin] here"}
    assert (await g.session().check_output("nothing")).action == "allow"


async def test_log_action_runs_the_tool():
    sink = MemorySink()
    g = Guard(policy(rule("l", tool("issue_refund"), action="log")), sink=sink)
    refund, _, calls = refund_tools(g)
    await refund("o", 1, session=g.session())
    assert calls == [1] and sink.records[0].action == "log"


async def test_tool_errors_are_recorded_and_reraised():
    g = Guard(policy())

    @g.tool()
    def boom() -> None:
        raise RuntimeError("down")

    s = g.session()
    with pytest.raises(RuntimeError):
        await boom(session=s)
    assert s.events[-1].payload["ok"] is False


async def test_keyword_and_default_arguments_are_checked():
    g = Guard(policy(REFUND_CAP), on_block="return")

    @g.tool()
    def issue_refund(order_id: str, amount_cents: int = 99999) -> str:
        return "done"

    out = await issue_refund("o1", session=g.session())  # the default is over the cap
    assert out["error"] == "blocked_by_policy"
