from __future__ import annotations

import pytest
from policy_helpers import compile_seeded
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def test_compile_job_produces_a_draft_with_proposals(client, state):
    started = await compile_seeded(client, state)
    job = (await client.get(f"/v1/jobs/{started['job_id']}")).json()
    assert job["status"] == "done" and job["result"]["proposals"] == 11, job
    pid = started["policy_id"]

    one = (await client.get(f"/v1/policies/{pid}")).json()
    assert (one["version"], one["status"], one["name"]) == (1, "draft", "Support policy")
    assert one["policy"]["rules"] == [] and "Refund" in one["source_text"]

    props = (await client.get(f"/v1/policies/{pid}/proposals")).json()
    assert props["policy_id"] == pid and len(props["proposals"]) == 11
    assert {p["klass"] for p in props["proposals"]} == {"machine", "model"}
    assert all(p["status"] == "proposed" for p in props["proposals"])
    assert props["cost"]["usd_micros"] >= 0

    listing = (await client.get("/v1/policies")).json()
    assert [p["id"] for p in listing] == [pid]
    assert (await client.get(f"/v1/policies/{pid}?version=1")).json()["version"] == 1
    assert (await client.get(f"/v1/policies/{pid}?version=9")).status_code == 404


async def test_compile_validation_and_text_source(client, state):
    both = await client.post(
        "/v1/policies/compile", json={"name": "n", "text": "1. a", "agent_id": "x"}
    )
    assert both.status_code == 422
    assert (await client.post("/v1/policies/compile", json={"name": "n"})).status_code == 422
    assert (
        await client.post("/v1/policies/compile", json={"name": "n", "agent_id": "nope"})
    ).status_code == 404
    bad_world = {"name": "n", "text": "1. a", "tools_from_world_id": "nope"}
    assert (await client.post("/v1/policies/compile", json=bad_world)).status_code == 404
    ok = await client.post("/v1/policies/compile", json={"name": "n", "text": "1. Be nice."})
    assert ok.status_code == 202 and ok.json()["policy_id"].startswith("pol_")


async def test_coverage_counts_add_up(client, state):
    pid = (await compile_seeded(client, state))["policy_id"]
    cov = (await client.get(f"/v1/policies/{pid}/coverage")).json()
    assert cov["clauses_total"] == 11
    assert cov["machine"] + cov["model"] + cov["human"] == 11
    assert len(cov["uncovered"]) == 11 and len(cov["by_clause"]) == 11  # nothing accepted yet
    assert cov["rules_exercised"] == [] and cov["rules_untested"] == []


async def test_coverage_with_run_trajectories(client, state):
    from api_helpers import new_run

    started = await compile_seeded(client, state)
    pid = started["policy_id"]
    props = (await client.get(f"/v1/policies/{pid}/proposals")).json()["proposals"]
    first = next(p for p in props if p["klass"] == "machine")
    r = await client.patch(
        f"/v1/policies/{pid}/proposals/{first['clause_id']}", json={"status": "accepted"}
    )
    assert r.status_code == 200
    run_id = await new_run(client, state, started["seed"], repetitions=1)
    cov = (await client.get(f"/v1/policies/{pid}/coverage", params={"run_id": run_id})).json()
    assert cov["trajectories"] > 0
    assert len(cov["rules_exercised"]) + len(cov["rules_untested"]) == 1
    missing = await client.get(f"/v1/policies/{pid}/coverage", params={"run_id": "nope"})
    assert missing.status_code == 404


async def test_policies_are_workspace_scoped(client, state, sm):
    pid = (await compile_seeded(client, state))["policy_id"]
    async with sm() as s, s.begin():
        await s.execute(text("INSERT INTO workspaces (id, name) VALUES ('ws_other', 'o')"))
        await s.execute(text("UPDATE policy_proposals SET workspace_id = 'ws_other'"))
        await s.execute(text("UPDATE policies SET workspace_id = 'ws_other'"))
    for path in ("", "/proposals", "/coverage"):
        assert (await client.get(f"/v1/policies/{pid}{path}")).status_code == 404
    assert (await client.get("/v1/policies")).json() == []
    assert (
        await client.patch(f"/v1/policies/{pid}/proposals/c01", json={"status": "accepted"})
    ).status_code == 404
    assert (await client.post(f"/v1/policies/{pid}/publish")).status_code == 404
