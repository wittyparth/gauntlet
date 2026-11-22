"""Seed, run, worker, SSE and report against the compose Postgres and Redis."""

from __future__ import annotations

import asyncio
import json

import pytest
from gauntlet_core.eval import RunReport
from gauntlet_server.worker import Worker

pytestmark = pytest.mark.integration


async def sse_events(client, run_id):
    out = []
    async with client.stream("GET", f"/v1/runs/{run_id}/stream") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        name = None
        async for line in r.aiter_lines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: ") and name:
                out.append((name, json.loads(line[6:])))
                if name == "run_update" and out[-1][1]["status"] in ("done", "cancelled"):
                    break
    return out


async def test_seed_report_and_episode_detail(client):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    again = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    assert again["run_id"] == seed["run_id"]
    rep = RunReport.model_validate((await client.get(f"/v1/runs/{seed['run_id']}/report")).json())
    assert rep.counted == 10 and rep.excluded == {}
    ep = (await client.get(f"/v1/episodes/{seed['failed_episode_id']}")).json()
    assert ep["outcome"] == "failed" and not ep["partial"]
    assert any(e["kind"] == "tool_result" and e["payload"]["patch"] for e in ep["events"])
    fail = next(v for v in ep["verdicts"] if v["result"] == "fail")
    cited = next(e for e in ep["events"] if e["seq"] == fail["evidence"][0]["seq"])
    assert fail["evidence"][0]["quote"] in json.dumps(cited["payload"])
    assert ep["diff"]["changes"]


async def test_new_run_drained_by_workers_with_sse(client, state):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    r = await client.post(
        "/v1/runs",
        json={
            "suite_id": seed["suite_id"],
            "agent_version_id": seed["agent_version_id"],
            "budget_usd_micros": 2_000_000,
            "seed": 7,
        },
    )
    assert r.status_code == 201, r.text
    run_id = r.json()["id"]
    workers = [Worker(state, concurrency=2) for _ in range(2)]
    stop = asyncio.Event()
    tasks = [asyncio.create_task(w.run(stop)) for w in workers]
    try:
        events = await asyncio.wait_for(sse_events(client, run_id), 60)
    finally:
        stop.set()
        await asyncio.gather(*tasks)
    names = {n for n, _ in events}
    assert events[0][0] == "run_update" and "episode_update" in names
    assert events[-1][1]["status"] == "done"
    run = (await client.get(f"/v1/runs/{run_id}")).json()
    assert run["counts"]["by_outcome"] == {"passed": 9, "failed": 1}
    rep = RunReport.model_validate((await client.get(f"/v1/runs/{run_id}/report")).json())
    assert rep.counted == 10
    assert run["spent_usd_micros"] > 0 and run["reserved_usd_micros"] == 0


async def test_seed_replaces_a_stale_demo_run_from_an_older_seed(client, sm):
    """A dev database seeded before the ecommerce pack holds a `run_demo` of another suite;
    the seed must not keep serving it."""
    from sqlalchemy import text

    async with sm() as s, s.begin():
        await s.execute(
            text(
                "INSERT INTO runs (id, workspace_id, suite_id, agent_version_id, manifest, "
                "status, budget_usd_micros) VALUES ('run_demo', 'ws_test', 'suite_1', 'av_1', "
                "'{}', 'done', 1000)"
            )
        )
        await s.execute(
            text(
                "INSERT INTO episodes (id, workspace_id, run_id, scenario_id, status, outcome) "
                "VALUES ('ep_demo_0', 'ws_test', 'run_demo', 'demo_status_1', 'done', 'failed')"
            )
        )
    seed = (await client.post("/v1/dev/seed", json={})).json()
    run = (await client.get(f"/v1/runs/{seed['run_id']}")).json()
    assert run["suite_id"] == "ecommerce_smoke"
    assert run["counts"]["total"] == 10 and run["counts"]["by_outcome"] == {
        "passed": 9,
        "failed": 1,
    }
    assert seed["failed_episode_id"]
    ep = (await client.get(f"/v1/episodes/{seed['failed_episode_id']}")).json()
    assert ep["scenario_id"] == "scn_ecom_07" and ep["verdicts"]


async def test_seed_keeps_its_agent_version_current(client, sm):
    from sqlalchemy import text

    seed = (await client.post("/v1/dev/seed", json={})).json()
    async with sm() as s, s.begin():
        await s.execute(
            text(
                "UPDATE agent_versions SET config = jsonb_set(config, '{profile,purpose}', "
                "'\"old\"') WHERE id = 'agv_demo'"
            )
        )
    await client.post("/v1/dev/seed", json={})
    agent = (await client.get(f"/v1/agents/{seed['agent_id']}")).json()
    assert agent["purpose"] == "Customer support for an online outdoor gear store"


async def test_seed_creates_the_compare_run_only_when_asked(client):
    plain = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    assert plain["compare_run_id"] is None
    ids = [r["id"] for r in (await client.get("/v1/runs")).json()["items"]]
    assert ids == [plain["run_id"]]
    both = (await client.post("/v1/dev/seed", json={"compare_run": True})).json()
    assert both["compare_run_id"] == "run_demo_b"
    runs = {r["id"]: r for r in (await client.get("/v1/runs")).json()["items"]}
    assert (
        runs["run_demo_b"]["status"] == "done"
        and runs["run_demo_b"]["suite_id"] == runs["run_demo"]["suite_id"]
    )
    assert runs["run_demo_b"]["spent_usd_micros"] >= 0


async def test_seed_gateway_fixtures_are_opt_in_and_idempotent(client):
    plain = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    assert plain["policy_id"] is None and (await client.get("/v1/policies")).json() == []
    out = (await client.post("/v1/dev/seed", json={"gateway": True})).json()
    again = (await client.post("/v1/dev/seed", json={"gateway": True})).json()
    assert out["policy_id"] == again["policy_id"] == "pol_demo"
    pol = (await client.get("/v1/policies/pol_demo")).json()
    assert pol["status"] == "published" and len(pol["policy"]["rules"]) == 2
    props = (await client.get("/v1/policies/pol_demo/proposals")).json()
    assert [p["status"] for p in props["proposals"]] == ["accepted", "accepted", "proposed"]
    tests = (await client.get("/v1/policies/pol_demo/tests")).json()
    assert tests[0]["status"] == "done" and tests[0]["result"]["block_rate"] == 0.75
    dec = (await client.get("/v1/gateway/decisions")).json()["items"]
    assert len(dec) == 6 and {d["action"] for d in dec} >= {"block", "require_approval", "allow"}
    pending = (await client.get("/v1/gateway/approvals", params={"status": "pending"})).json()
    assert [a["id"] for a in pending] == ["gap_demo"]
    stats = (await client.get("/v1/gateway/stats")).json()
    assert stats["total"] == 6
