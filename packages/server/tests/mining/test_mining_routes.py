from __future__ import annotations

import json

import pytest
from mining_helpers import EXFIL, chat_doc, ingest, mine, mining_llm
from sqlalchemy import text

pytestmark = pytest.mark.integration

CARD = "4242 4242 4242 4242"


async def setup(client, state):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    agent = seed["agent_id"]
    state.gateway = mining_llm(judge_fail="useless")
    await ingest(client, chat_doc("leak", [("what is my card", f"Your card is {CARD}")]), agent)
    await ingest(client, chat_doc("exfil", [("hi", EXFIL)]), agent)
    await ingest(
        client,
        chat_doc("angry", [("where is my order", "soon"), ("this is useless", "sorry"),
                           ("talk to a human", "ok")]),
        agent,
    )  # fmt: skip
    await ingest(client, chat_doc("fine", [("hello", "hi there, how can I help?")]), agent)
    return seed


async def test_mining_ranks_candidates_and_clusters_them(client, state):
    seed = await setup(client, state)
    out = await mine(client, state, seed["agent_id"], limit=10)
    run = (await client.get(f"/v1/production/mine/{out['mining_run_id']}")).json()
    assert (
        run["status"] == "done"
        and run["counts"]["scanned"] == 4
        and run["counts"]["candidates"] == 3
    )
    page = (
        await client.get("/v1/production/candidates", params={"mining_run_id": run["id"]})
    ).json()
    ids = [c["conversation_id"] for c in page["items"]]
    scores = [c["score"] for c in page["items"]]
    assert scores == sorted(scores, reverse=True) and len(ids) == 3  # "fine" is not a candidate
    by_part = {tuple(sorted(c["parts"])): c for c in page["items"]}
    assert ("redaction_leak",) in by_part and ("detector",) in by_part
    assert any(k for k in by_part if "human_request" in k)
    # the leak ranks above the angry user
    top = page["items"][0]
    assert top["parts"].keys() <= {"redaction_leak", "detector"} and top["status"] == "new"
    assert all(c["reasons"] for c in page["items"])
    detail = (await client.get(f"/v1/production/candidates/{top['id']}")).json()
    assert detail["events"] and CARD not in json.dumps(detail)


async def test_pagination_filters_and_scoping(client, state, sm):
    seed = await setup(client, state)
    out = await mine(client, state, seed["agent_id"], limit=10)
    q = {"mining_run_id": out["mining_run_id"]}
    p1 = (await client.get("/v1/production/candidates", params={**q, "limit": 2})).json()
    assert len(p1["items"]) == 2 and p1["next_cursor"]
    p2 = (
        await client.get(
            "/v1/production/candidates", params={**q, "limit": 2, "cursor": p1["next_cursor"]}
        )
    ).json()
    assert len(p2["items"]) == 1 and p2["next_cursor"] is None
    seen = [c["id"] for c in p1["items"] + p2["items"]]
    assert len(set(seen)) == 3
    assert (
        await client.get("/v1/production/candidates", params={**q, "status": "converted"})
    ).json()["items"] == []
    assert (
        await client.get("/v1/production/candidates", params={"cursor": "!!"})
    ).status_code == 422
    first = seen[0]
    dismissed = await client.post(f"/v1/production/candidates/{first}/dismiss")
    assert dismissed.status_code == 200 and dismissed.json()["status"] == "dismissed"
    assert (await client.post(f"/v1/production/candidates/{first}/convert")).status_code == 409
    async with sm() as s, s.begin():
        await s.execute(text("INSERT INTO workspaces (id, name) VALUES ('ws_other', 'o')"))
        await s.execute(text("UPDATE mining_candidates SET workspace_id = 'ws_other'"))
        await s.execute(text("UPDATE mining_runs SET workspace_id = 'ws_other'"))
    assert (await client.get(f"/v1/production/candidates/{first}")).status_code == 404
    assert (await client.get(f"/v1/production/mine/{out['mining_run_id']}")).status_code == 404
    assert (await client.get("/v1/production/candidates")).json()["items"] == []


async def test_a_budget_is_required_and_inputs_are_validated(client, state):
    seed = await setup(client, state)
    agent = seed["agent_id"]
    assert (await client.post("/v1/production/mine", json={"agent_id": agent})).status_code == 422
    zero = await client.post(
        "/v1/production/mine", json={"agent_id": agent, "budget_usd_micros": 0}
    )
    assert zero.status_code == 422
    nope = await client.post(
        "/v1/production/mine", json={"agent_id": "agt_nope", "budget_usd_micros": 5}
    )
    assert nope.status_code == 404
    bad = await client.post(
        "/v1/production/mine",
        json={"agent_id": agent, "budget_usd_micros": 5, "detectors": ["nope"]},
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "unknown_detector"
    uncal = await client.post(
        "/v1/production/mine",
        json={"agent_id": agent, "budget_usd_micros": 5, "rubric_id": "task_completion"},
    )
    assert uncal.status_code in (404, 422)


async def test_the_judge_needs_a_calibrated_rubric_and_respects_the_budget(client, state, sm):
    seed = await setup(client, state)
    rubric = {
        "id": "polite", "version": 1, "title": "Polite", "question": "Was the agent polite?",
        "pass_definition": "yes", "fail_definition": "no",
    }  # fmt: skip
    async with sm() as s, s.begin():
        await s.execute(
            text(
                "INSERT INTO rubrics (id, version, workspace_id, doc) "
                "VALUES ('polite', 1, 'ws_test', CAST(:d AS jsonb))"
            ),
            {"d": json.dumps(rubric)},
        )
    body = {"agent_id": seed["agent_id"], "budget_usd_micros": 10_000, "rubric_id": "polite"}
    refused = await client.post("/v1/production/mine", json=body)
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "rubric_not_calibrated"
    async with sm() as s, s.begin():
        await s.execute(
            text(
                "INSERT INTO calibrations (id, workspace_id, rubric_id, rubric_version, status, "
                "gating_allowed, stale) "
                "VALUES ('cal_1', 'ws_test', 'polite', 1, 'done', true, false)"
            )
        )
    out = await mine(
        client, state, seed["agent_id"], rubric_id="polite", judge_sample=1.0, limit=10
    )
    page = (
        await client.get(
            "/v1/production/candidates", params={"mining_run_id": out["mining_run_id"]}
        )
    ).json()
    angry = next(c for c in page["items"] if "human_request" in c["parts"])
    assert angry["parts"]["judge"] == 1.0  # the fake judge fails "useless"
    assert out["job"]["result"]["judged"] == 4 and out["job"]["result"]["spent_usd_micros"] >= 400
    # a tiny budget stops the judge part-way and says so
    out2 = await mine(client, state, seed["agent_id"], rubric_id="polite", judge_sample=1.0,
                      budget_usd_micros=150, limit=10)  # fmt: skip
    res = out2["job"]["result"]
    assert res["judged"] < 4 and res["budget_exhausted"] == 1


async def test_without_a_rubric_no_judge_call_is_made(client, state):
    seed = await setup(client, state)
    llm = state.gateway
    await mine(client, state, seed["agent_id"], limit=10)
    assert all(c.role != "judge_small" for c in llm.calls)
