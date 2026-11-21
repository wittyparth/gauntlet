"""Kill switch: API effects and the in-flight cancellation (5 second requirement)."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest
from atk_helpers import make_attack_suite, make_turn_suite, make_version, run_body
from gauntlet_server.worker import Worker
from sqlalchemy import text

pytestmark = pytest.mark.integration
LOCAL = "http://localhost:9/v1"


class RecordingAgent:
    """A target that records every request and (optionally) never answers."""

    def __init__(self, hang: bool = False) -> None:
        self.hang, self.times, self.started = hang, [], asyncio.Event()

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.times.append(time.monotonic())
        self.started.set()
        if self.hang:
            await asyncio.Event().wait()
        return httpx.Response(200, json={"choices": [{"message": {"content": "ord_1001 shipped"}}]})


async def episode_rows(state, run_id):
    async with state.sm() as s:
        rows = await s.execute(
            text("SELECT status, outcome FROM episodes WHERE run_id = :r"), {"r": run_id}
        )
        return [tuple(r) for r in rows]


async def test_engage_rejects_new_attack_runs_and_release_permits(client, state):
    version = await make_version(client, LOCAL)
    suite = await make_attack_suite(client, state)
    r = await client.post("/v1/killswitch", json={"scope": "workspace", "reason": "drill"})
    assert r.status_code == 201 and r.json()["engaged"] is True
    blocked = await client.post("/v1/runs", json=run_body(suite, version))
    assert blocked.status_code == 423 and blocked.json()["error"]["code"] == "killswitch_engaged"
    assert (await client.delete("/v1/killswitch?scope=workspace")).json()["engaged"] is False
    assert (await client.post("/v1/runs", json=run_body(suite, version))).status_code == 201
    actions = [x["action"] for x in (await client.get("/v1/audit")).json()["items"]]
    assert {"killswitch.engaged", "killswitch.released", "attack_run.created"} <= set(actions)
    assert (await client.get("/v1/audit/verify")).json()["ok"] is True


async def test_engage_cancels_queued_attack_episodes_and_spares_benign_runs(client, state):
    version = await make_version(client, LOCAL)
    suite = await make_attack_suite(client, state)
    attack_run = (await client.post("/v1/runs", json=run_body(suite, version))).json()["id"]
    benign = await client.post(
        "/v1/runs", json=run_body("ecommerce_smoke", version, budget_usd_micros=5_000_000)
    )
    assert benign.status_code == 201, benign.text
    await client.post("/v1/killswitch", json={"scope": "workspace", "reason": "stop"})
    run = (await client.get(f"/v1/runs/{attack_run}")).json()
    assert run["status"] == "cancelled" and run["counts"]["cancelled"] == 1
    assert run["counts"]["by_outcome"] == {}  # cancelled episodes have no outcome (CQ-S5)
    other = (await client.get(f"/v1/runs/{benign.json()['id']}")).json()
    assert other["status"] == "queued" and other["counts"]["cancelled"] == 0


async def test_run_scope_only_affects_that_run(client, state):
    version = await make_version(client, LOCAL)
    suite = await make_attack_suite(client, state)
    a = (await client.post("/v1/runs", json=run_body(suite, version))).json()["id"]
    b = (await client.post("/v1/runs", json=run_body(suite, version))).json()["id"]
    r = await client.post("/v1/killswitch", json={"scope": "run", "run_id": a, "reason": "x"})
    assert r.status_code == 201
    assert (await client.get(f"/v1/runs/{a}")).json()["status"] == "cancelled"
    assert (await client.get(f"/v1/runs/{b}")).json()["status"] == "queued"
    assert (await client.get("/v1/killswitch")).json()["switches"][0]["run_id"] == a


async def test_engaging_stops_an_in_flight_campaign_within_five_seconds(client, state):
    version = await make_version(client, LOCAL)
    suite = await make_turn_suite(client, state)
    run_id = (await client.post("/v1/runs", json=run_body(suite, version))).json()["id"]
    agent = RecordingAgent(hang=True)
    http = httpx.AsyncClient(transport=httpx.MockTransport(agent))
    worker = Worker(state, concurrency=1, poll_interval_s=0.05, http=http)
    stop = asyncio.Event()
    task = asyncio.create_task(worker.run(stop))
    try:
        await asyncio.wait_for(agent.started.wait(), 20)
        engaged_at = time.monotonic()
        await client.post("/v1/killswitch", json={"scope": "workspace", "reason": "stop"})
        rows: list = []
        for _ in range(100):
            rows = await episode_rows(state, run_id)
            if rows and rows[0][0] == "cancelled":
                break
            await asyncio.sleep(0.1)
        assert rows == [("cancelled", None)]
        assert time.monotonic() - engaged_at < 5
        assert len(agent.times) == 1  # no target traffic after the engagement
        assert (await client.get(f"/v1/runs/{run_id}")).json()["status"] == "cancelled"
        await asyncio.sleep(1.2)
        assert len(agent.times) == 1
    finally:
        stop.set()
        await asyncio.wait_for(task, 10)
