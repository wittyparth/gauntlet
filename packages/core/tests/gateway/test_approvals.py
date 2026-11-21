# pyright: reportOptionalMemberAccess=false
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import httpx
import pytest
from gauntlet_core.gateway import (
    ApprovalExpired,
    CallbackApprovals,
    Guard,
    HttpApprovals,
    MemorySink,
)
from gw_helpers import policy, rule, tool

PAY = rule("pay-approval", tool("pay"), action="require_approval", message="needs a human")


async def run(handler, **kw):
    sink = MemorySink()
    g = Guard(policy(PAY), sink=sink, approvals=handler, **kw)
    s = g.session()
    d = await s.check_tool_call("pay", {"amount": 5})
    return d, sink.records[0], s


async def test_callback_approve_and_deny():
    seen = []

    def approve(decision, record):
        seen.append((decision.rule_id, record.tool, record.approval.id))
        return "approved"

    d, rec, s = await run(CallbackApprovals(approve))
    assert d.action == "allow" and d.rule_id == "pay-approval"
    assert rec.action == "require_approval" and rec.approval.outcome == "approved"
    assert rec.approval.id.startswith("gap_") and seen[0][:2] == ("pay-approval", "pay")
    assert [e.kind for e in s.events] == ["tool_call"]  # it went ahead

    async def deny(decision, record):
        return False

    d, rec, s = await run(CallbackApprovals(deny))
    assert d.action == "block" and rec.approval.outcome == "denied"
    assert s.events == []  # a denied call never happened


@pytest.mark.parametrize(("on_timeout", "expect"), [("deny", "block"), ("allow", "allow")])
async def test_expiry_follows_on_timeout(on_timeout, expect):
    class Expires:
        async def request(self, decision, record):
            raise ApprovalExpired("gap_x")

    d, rec, _ = await run(Expires(), on_timeout=on_timeout)
    assert d.action == expect and rec.approval.outcome == "expired"


def fake_server(statuses: list[str]):
    log: list[tuple[str, str]] = []
    state = {"polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        log.append((request.method, request.url.path))
        if request.method == "POST":
            import json

            body = json.loads(request.content)
            log.append(("body", json.dumps(body["record"]["tool"])))
            assert request.headers["authorization"] == "Bearer k"
            return httpx.Response(201, json={"id": body["id"], "status": "pending"})
        status = statuses[min(state["polls"], len(statuses) - 1)]
        state["polls"] += 1
        return httpx.Response(200, json={"id": "x", "status": status})

    return httpx.MockTransport(handler), log


@pytest.mark.parametrize(
    ("statuses", "action", "outcome"),
    [
        (["pending", "pending", "approved"], "allow", "approved"),
        (["denied"], "block", "denied"),
        (["pending", "expired"], "block", "expired"),
    ],
)
async def test_http_approvals_poll_until_decided(statuses, action, outcome):
    transport, log = fake_server(statuses)
    h = HttpApprovals("http://api.test", "k", poll_interval_s=0.001, transport=transport)
    d, rec, _ = await run(h)
    await h.aclose()
    assert d.action == action and rec.approval.outcome == outcome
    assert log[0] == ("POST", "/v1/gateway/approvals") and ("body", '"pay"') in log
    assert ("GET", f"/v1/gateway/approvals/{rec.approval.id}") in log


async def test_http_approvals_server_error_follows_on_timeout():
    def handler(request):
        return httpx.Response(503)

    h = HttpApprovals("http://api.test", "k", transport=httpx.MockTransport(handler))
    d, rec, _ = await run(h, on_timeout="allow")
    await h.aclose()
    assert d.action == "allow" and rec.approval.outcome == "expired"
