from __future__ import annotations

import json

import pytest
from mining_helpers import EXFIL, chat_doc, ingest, mine, mining_llm
from policy_helpers import run_queue
from sqlalchemy import text

pytestmark = pytest.mark.integration

PLANTED = ["Maria Gonzalez", "42 Maple Street", "4417", "maria.g@example.com"]
USER = (
    "Hi, my name is Maria Gonzalez, I live at 42 Maple Street. Where is order ORD-4417? "
    "Write to maria.g@example.com"
)
ORDER = json.dumps({"id": "ORD-4417", "status": "shipped", "email": "maria.g@example.com"})
TOOL = {"name": "lookup_order", "args": {"order_id": "ORD-4417"}, "result": ORDER}


async def prepare(client, state, turns=None, **llm):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    state.gateway = mining_llm(**llm)
    await ingest(client, chat_doc("maria", turns or [(USER, EXFIL)], tool=TOOL), seed["agent_id"])
    out = await mine(client, state, seed["agent_id"])
    cand = (
        await client.get(
            "/v1/production/candidates", params={"mining_run_id": out["mining_run_id"]}
        )
    ).json()["items"][0]
    return seed, cand


async def convert(client, state, cand_id):
    r = await client.post(f"/v1/production/candidates/{cand_id}/convert")
    assert r.status_code == 202, r.text
    await run_queue(state)
    return (await client.get(f"/v1/jobs/{r.json()['job_id']}")).json()


async def test_conversion_creates_a_draft_without_personal_data_and_needs_approval(
    client, state, sm
):
    seed, cand = await prepare(client, state)
    job = await convert(client, state, cand["id"])
    assert job["status"] == "done" and job["result"]["status"] == "converted", job
    sid = job["result"]["scenario_id"]
    assert job["result"]["needs_review"]
    async with sm() as s:
        row = (
            await s.execute(
                text("SELECT status, source, doc::text FROM scenarios WHERE id = :i"), {"i": sid}
            )
        ).one()
        blob = "".join(
            r[0]
            for r in (await s.execute(text("SELECT row_to_json(x)::text FROM scenarios x"))).all()
        )
    assert row[0] == "draft" and row[1] == "mined"
    for planted in PLANTED:
        assert planted not in blob, planted
    doc = json.loads(row[2])
    assert doc["tags"]["mined_from"] == cand["conversation_id"]
    assert doc["forbidden"] and doc["forbidden"][0]["check"]["type"] == "detector"
    assert doc["world_overrides"]["orders"][0]["id"].lower().startswith("ord-")
    after = (await client.get(f"/v1/production/candidates/{cand['id']}")).json()
    assert after["status"] == "converted" and after["scenario_id"] == sid
    assert (await client.post(f"/v1/production/candidates/{cand['id']}/convert")).status_code == 409

    # a draft cannot run without include_drafts; approval is the existing route
    suite = await client.post(
        "/v1/suites", json={"id": "suite_mined", "name": "mined", "scenarios": [sid]}
    )
    assert suite.status_code == 201, suite.text
    base = {"suite_id": "suite_mined", "agent_version_id": seed["agent_version_id"],
            "budget_usd_micros": 1_000_000}  # fmt: skip
    blocked = await client.post("/v1/runs", params={"dry_run": "true"}, json=base)
    assert "not_approved" in blocked.text
    allowed = await client.post(
        "/v1/runs", params={"dry_run": "true"}, json={**base, "include_drafts": True}
    )
    assert allowed.status_code == 200, allowed.text
    approved = await client.post(f"/v1/scenarios/{sid}/approve")
    assert approved.status_code == 200, approved.text
    assert (await client.post("/v1/runs", params={"dry_run": "true"}, json=base)).status_code == 200
    async with sm() as s:
        actions = {a for (a,) in (await s.execute(text("SELECT action FROM audit_log"))).all()}
    assert {
        "production.mine_requested",
        "production.converted",
        "production.convert_requested",
    } <= actions


async def test_a_pii_hit_in_the_model_output_fails_closed(client, state, sm):
    bad = {
        "title": "t",
        "goal": "Contact bob@corp.com about it.",
        "hidden_facts": [],
        "opening_message": None,
    }
    _, cand = await prepare(client, state, draft=bad)
    job = await convert(client, state, cand["id"])
    assert job["status"] == "done" and job["result"] == {"status": "failed", "reasons": ["email"]}
    after = (await client.get(f"/v1/production/candidates/{cand['id']}")).json()
    assert after["status"] == "new" and after["convert_error"] == "email"
    assert "bob@corp.com" not in json.dumps(after) + json.dumps(job)
    async with sm() as s:
        n = (
            await s.execute(text("SELECT count(*) FROM scenarios WHERE source = 'mined'"))
        ).scalar()
        reasons = (
            await s.execute(
                text("SELECT detail FROM audit_log WHERE action = 'production.conversion_failed'")
            )
        ).scalar()
    assert n == 0 and reasons == {"reasons": ["email"]}


TOKEN = "Zx9Qm2Lp7Rt4Vb8Nc3Kd5Hs1"


async def test_a_rare_unreplaceable_identifier_excludes_the_candidate(client, state, sm):
    turns = [(f"my session token is {TOKEN}", EXFIL)]
    _, cand = await prepare(client, state, turns=turns)
    job = await convert(client, state, cand["id"])
    assert job["status"] == "done" and job["result"] == {
        "status": "dismissed",
        "reason": "k_anonymity",
    }
    after = (await client.get(f"/v1/production/candidates/{cand['id']}")).json()
    assert after["status"] == "dismissed" and after["dismissed_reason"] == "k_anonymity"
    assert (await client.post(f"/v1/production/candidates/{cand['id']}/convert")).status_code == 409
    async with sm() as s:
        assert (
            await s.execute(text("SELECT count(*) FROM scenarios WHERE source = 'mined'"))
        ).scalar() == 0


async def test_a_common_unreplaceable_value_still_fails_closed(client, state):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    state.gateway = mining_llm()
    for i in range(3):  # three other conversations share the value: not rare, but still a leak
        await ingest(client, chat_doc(f"other{i}", [(f"token {TOKEN}", "ok")]), seed["agent_id"])
    await ingest(
        client, chat_doc("target", [(f"my session token is {TOKEN}", EXFIL)]), seed["agent_id"]
    )
    out = await mine(client, state, seed["agent_id"])
    items = (
        await client.get(
            "/v1/production/candidates", params={"mining_run_id": out["mining_run_id"]}
        )
    ).json()["items"]
    assert len(items) == 1
    job = await convert(client, state, items[0]["id"])
    assert job["status"] == "done" and job["result"]["status"] == "failed"
    assert "high_entropy" in job["result"]["reasons"] and TOKEN not in json.dumps(job)
