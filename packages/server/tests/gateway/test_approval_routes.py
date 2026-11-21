from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx
import pytest
from gauntlet_core.gateway import Guard, HttpApprovals, HttpSink
from gauntlet_core.schema import Policy
from gauntlet_server.app import create_app
from gauntlet_server.services.gateway import expire_approvals_all
from sqlalchemy import text

pytestmark = pytest.mark.integration


def record(**kw) -> dict:
    base = {
        "id": "gdc_1",
        "ts": datetime.now(UTC).isoformat(),
        "session_id": "ses_1",
        "policy_id": "pol_a",
        "policy_version": 1,
        "mode": "enforce",
        "kind": "tool_call",
        "tool": "issue_refund",
        "args": {"amount_cents": 20000},
        "action": "require_approval",
        "enforced": True,
        "rule_id": "refund-approval",
        "message": "needs a human",
    }
    return {**base, **kw}


async def create(client, **body):
    r = await client.post("/v1/gateway/approvals", json={"record": record(), **body})
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_get_list_and_default_expiry(client):
    a = await create(client)
    assert a["status"] == "pending" and a["id"].startswith("gap_")
    assert a["decision"]["tool"] == "issue_refund" and a["decision"]["args"] == {
        "amount_cents": 20000
    }
    exp = datetime.fromisoformat(a["expires_at"])
    req = datetime.fromisoformat(a["requested_at"])
    assert 14 * 60 < (exp - req).total_seconds() < 16 * 60  # CQ-G2: 15 minutes
    assert (await client.get(f"/v1/gateway/approvals/{a['id']}")).json()["status"] == "pending"
    listed = (await client.get("/v1/gateway/approvals", params={"status": "pending"})).json()
    assert [x["id"] for x in listed] == [a["id"]]
    assert (await client.get("/v1/gateway/approvals", params={"status": "approved"})).json() == []
    assert (await client.get("/v1/gateway/approvals/gap_nope")).status_code == 404
    short = await create(client, expires_in_s=30)
    delta = datetime.fromisoformat(short["expires_at"]) - datetime.fromisoformat(
        short["requested_at"]
    )
    assert 29 <= delta.total_seconds() <= 31
    bad = await client.post("/v1/gateway/approvals", json={"record": record(), "expires_in_s": 0})
    assert bad.status_code == 422


async def test_client_supplied_id_is_idempotent(client):
    first = await create(client, id="gap_abcdefgh01")
    again = await create(client, id="gap_abcdefgh01")
    assert first["id"] == again["id"] == "gap_abcdefgh01"
    assert len((await client.get("/v1/gateway/approvals")).json()) == 1
    bad = await client.post("/v1/gateway/approvals", json={"record": record(), "id": "nope"})
    assert bad.status_code == 422


async def test_decide_is_idempotent_and_audited_once(client, sm):
    a = await create(client)
    url = f"/v1/gateway/approvals/{a['id']}/decide"
    r = await client.post(url, json={"decision": "approve", "note": "ok by me"})
    assert r.status_code == 200
    body = r.json()
    assert (body["status"], body["note"], body["decided_by"]) == ("approved", "ok by me", "t")
    assert body["decided_at"]
    same = await client.post(url, json={"decision": "approve"})
    assert same.status_code == 200 and same.json()["status"] == "approved"
    assert same.json()["note"] == "ok by me"  # the first decision stands
    opposite = await client.post(url, json={"decision": "deny"})
    assert opposite.status_code == 409 and opposite.json()["error"]["code"] == "conflict"
    async with sm() as s:
        n = (
            await s.execute(
                text(
                    "SELECT count(*) FROM audit_log WHERE action = 'gateway.approval_decided' "
                    "AND subject_id = :i"
                ),
                {"i": a["id"]},
            )
        ).scalar()
    assert n == 1
    assert (await client.post(url, json={"decision": "maybe"})).status_code == 422


async def test_deny(client):
    a = await create(client)
    r = await client.post(f"/v1/gateway/approvals/{a['id']}/decide", json={"decision": "deny"})
    assert r.json()["status"] == "denied"


async def expire_now(sm, approval_id):
    async with sm() as s, s.begin():
        await s.execute(
            text(
                "UPDATE gateway_approvals SET expires_at = now() - interval '1 minute' "
                "WHERE id = :i"
            ),
            {"i": approval_id},
        )


async def test_expired_cannot_be_decided(client, sm):
    a = await create(client)
    await expire_now(sm, a["id"])
    got = (await client.get(f"/v1/gateway/approvals/{a['id']}")).json()
    assert got["status"] == "expired"  # lazily, on read
    r = await client.post(f"/v1/gateway/approvals/{a['id']}/decide", json={"decision": "approve"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "approval_expired"
    assert (await client.get("/v1/gateway/approvals", params={"status": "pending"})).json() == []


async def test_worker_sweep_expires_pending(client, sm, state):
    a, b = await create(client), await create(client)
    await expire_now(sm, a["id"])
    assert await expire_approvals_all(state) == 1
    async with sm() as s:
        rows = dict((await s.execute(text("SELECT id, status FROM gateway_approvals"))).all())
    assert rows == {a["id"]: "expired", b["id"]: "pending"}


async def test_approvals_are_workspace_scoped(client, sm):
    a = await create(client)
    async with sm() as s, s.begin():
        await s.execute(text("INSERT INTO workspaces (id, name) VALUES ('ws_other', 'o')"))
        await s.execute(text("UPDATE gateway_approvals SET workspace_id = 'ws_other'"))
    assert (await client.get(f"/v1/gateway/approvals/{a['id']}")).status_code == 404
    assert (
        await client.post(f"/v1/gateway/approvals/{a['id']}/decide", json={"decision": "approve"})
    ).status_code == 404
    assert (await client.get("/v1/gateway/approvals")).json() == []
    clash = await client.post("/v1/gateway/approvals", json={"record": record(), "id": a["id"]})
    assert clash.status_code == 409


async def test_sdk_end_to_end_decisions_and_http_approval(client, state):
    """The SDK talks to the real API in-process: records land in /decisions and a
    require_approval call waits until someone decides it over HTTP."""
    policy = Policy.model_validate(
        {
            "id": "pol_e2e",
            "mode": "enforce",
            "rules": [
                {
                    "id": "refund-cap",
                    "description": "cap",
                    "when": {
                        "type": "tool_called",
                        "tool": "issue_refund",
                        "args": {"amount_cents": {"gt": 20000}},
                    },
                    "action": "block",
                },
                {
                    "id": "refund-approval",
                    "description": "big refunds need approval",
                    "when": {
                        "type": "tool_called",
                        "tool": "issue_refund",
                        "args": {"amount_cents": {"gt": 10000}},
                    },
                    "action": "require_approval",
                    "message": "needs a human",
                    "severity": "medium",
                },
            ],
        }
    )
    transport = httpx.ASGITransport(app=create_app(state))
    sink = HttpSink("http://api.test", "gk_test_key", flush_interval_s=0.05, transport=transport)
    approvals = HttpApprovals(
        "http://api.test", "gk_test_key", poll_interval_s=0.02, expires_in_s=60, transport=transport
    )
    guard = Guard(policy, sink=sink, approvals=approvals, agent_id="agent_x")
    session = guard.session("ses_e2e")

    assert (
        await session.check_tool_call("issue_refund", {"amount_cents": 30000})
    ).action == "block"

    waiting = asyncio.create_task(session.check_tool_call("issue_refund", {"amount_cents": 15000}))
    pending = []
    for _ in range(200):
        pending = (await client.get("/v1/gateway/approvals", params={"status": "pending"})).json()
        if pending:
            break
        await asyncio.sleep(0.02)
    assert len(pending) == 1 and not waiting.done()
    assert pending[0]["decision"]["tool"] == "issue_refund"
    done = await client.post(
        f"/v1/gateway/approvals/{pending[0]['id']}/decide", json={"decision": "approve"}
    )
    assert done.status_code == 200
    d = await asyncio.wait_for(waiting, 5)
    assert d.action == "allow" and d.rule_id == "refund-approval"

    await sink.aclose()
    await approvals.aclose()
    items = (await client.get("/v1/gateway/decisions", params={"policy_id": "pol_e2e"})).json()[
        "items"
    ]
    by_action = sorted(i["action"] for i in items)
    assert by_action == ["block", "require_approval"]
    approved = next(i for i in items if i["action"] == "require_approval")
    assert approved["approval"]["outcome"] == "approved" and approved["agent_id"] == "agent_x"
    assert approved["approval"]["id"] == pending[0]["id"]
