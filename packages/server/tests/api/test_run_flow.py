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
