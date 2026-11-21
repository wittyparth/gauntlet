import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import asyncio

import pytest
from gauntlet_core.gateway import CallbackApprovals, Guard, MemorySink
from gw_helpers import REFUND_CAP, policy, rule, tool


def broken(guard: Guard) -> None:
    def boom(prefix, proposed):
        raise RuntimeError("engine bug")

    guard.snapshot()[1].decide = boom  # type: ignore[method-assign]


@pytest.mark.parametrize(
    ("fail", "expect"),
    [("open", "allow"), ("closed", "block")],
)
async def test_engine_failure_follows_the_fail_mode(fail, expect):
    sink = MemorySink()
    g = Guard(policy(REFUND_CAP, fail=fail), sink=sink)
    broken(g)
    d = await g.session().check_tool_call("issue_refund", {"amount_cents": 1})
    assert d.action == expect
    rec = sink.records[0]
    assert "engine bug" in (rec.guard_error or "")
    if expect == "block":
        assert d.message == "policy engine unavailable"


async def test_engine_failure_in_shadow_mode_never_blocks():
    sink = MemorySink()
    g = Guard(policy(REFUND_CAP, mode="shadow", fail="closed"), sink=sink)
    broken(g)
    d = await g.session().check_tool_call("x", {})
    assert d.action == "allow" and sink.records[0].would_have == "block"


class BadSink:
    async def write(self, record):
        raise OSError("disk full")


async def test_sink_down_does_not_raise():
    g = Guard(policy(REFUND_CAP), sink=BadSink())
    d = await g.session().check_tool_call("issue_refund", {"amount_cents": 20000})
    assert d.action == "block"
    assert g.sink_errors == 1


class BrokenTransport:
    async def request(self, decision, record):
        raise ConnectionError("approval service down")


@pytest.mark.parametrize(("on_timeout", "expect"), [("deny", "block"), ("allow", "allow")])
async def test_approval_transport_down_follows_on_timeout(on_timeout, expect):
    sink = MemorySink()
    pol = policy(rule("a", tool("pay"), action="require_approval"))
    g = Guard(pol, sink=sink, approvals=BrokenTransport(), on_timeout=on_timeout)
    d = await g.session().check_tool_call("pay", {})
    assert d.action == expect
    rec = sink.records[0]
    assert rec.approval is not None and rec.approval.outcome == "expired"
    assert "approval transport" in (rec.guard_error or "")


async def test_no_approval_handler_denies():
    g = Guard(policy(rule("a", tool("pay"), action="require_approval")))
    d = await g.session().check_tool_call("pay", {})
    assert d.action == "block" and "denied" in (d.message or "")


async def test_slow_approval_times_out():
    async def slow(decision, record):
        await asyncio.sleep(5)
        return "approved"

    g = Guard(
        policy(rule("a", tool("pay"), action="require_approval")),
        approvals=CallbackApprovals(slow),
        approval_timeout_s=0.05,
    )
    d = await g.session().check_tool_call("pay", {})
    assert d.action == "block"
