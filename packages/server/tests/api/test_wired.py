"""A wired agent calling the api-process mock facade; a worker killed mid-turn; resume."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from gauntlet_server.app import create_app
from gauntlet_server.worker import Worker
from sqlalchemy import text

pytestmark = pytest.mark.integration


class WiredAgent:
    """An OpenAI-compatible agent that looks the order up through the facade. While `block`
    is set it stalls after the tool call (the worker is 'killed mid-turn')."""

    def __init__(self, app) -> None:
        self.app, self.block, self.reached = app, False, asyncio.Event()
        self.tokens: list[str] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        token = request.headers["x-gauntlet-episode"]
        self.tokens.append(token)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://api.test"
        ) as c:
            r = await c.post(f"/mock/{token}/tools/lookup_order", json={"order_id": "ord_1"})
        assert r.status_code == 200, r.text
        if self.block:
            self.reached.set()
            await asyncio.Event().wait()
        status = r.json()["result"]["status"]
        content = f"Order ord_1 is {status}."
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


async def make_wired_run(client, seed) -> str:
    agent = (
        await client.post("/v1/agents", json={"project_id": seed["project_id"], "name": "W"})
    ).json()
    ver = await client.post(
        f"/v1/agents/{agent['id']}/versions",
        json={
            "label": "wired",
            "target": {
                "kind": "openai_compat",
                "base_url": "http://agent.test/v1",
                "model": "m",
                "wired": True,
            },
            "profile": {"purpose": "orders"},
            "world_id": "shop",
        },
    )
    assert ver.status_code == 201, ver.text
    r = await client.post(
        "/v1/suites", json={"id": "suite_wired", "name": "w", "scenarios": ["demo_status_1"]}
    )
    assert r.status_code == 201, r.text
    run = await client.post(
        "/v1/runs",
        json={
            "suite_id": "suite_wired",
            "agent_version_id": ver.json()["id"],
            "budget_usd_micros": 1_000_000,
            "seed": 3,
        },
    )
    assert run.status_code == 201, run.text
    return run.json()["id"]


async def wait_done(client, run_id, timeout=30.0):
    for _ in range(int(timeout / 0.1)):
        run = (await client.get(f"/v1/runs/{run_id}")).json()
        if run["status"] == "done":
            return run
        await asyncio.sleep(0.1)
    raise AssertionError("run did not finish")


async def test_facade_rejects_bad_and_stale_tokens(client, state):
    app = create_app(state)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://api.test"
    ) as c:
        assert (await c.post("/mock/bad.1.sig/tools/lookup_order", json={})).status_code == 401
        assert (await c.post("/mock/x.1.y/mcp", json={})).status_code in (401, 501)


async def test_wired_episode_completes_and_resumes_after_worker_kill(client, state):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    run_id = await make_wired_run(client, seed)
    agent = WiredAgent(create_app(state))
    agent.block = True
    http = httpx.AsyncClient(transport=httpx.MockTransport(agent))

    a = Worker(state, concurrency=1, lease_s=1, http=http)
    task = asyncio.create_task(a.run())
    await asyncio.wait_for(agent.reached.wait(), 20)
    await a.kill()  # SIGKILL equivalent: no release, no writes
    await asyncio.gather(task, return_exceptions=True)
    old_token = agent.tokens[0]

    agent.block = False
    await asyncio.sleep(1.3)  # the lease expires
    stop = asyncio.Event()
    b = Worker(state, concurrency=1, lease_s=1, poll_interval_s=0.05, http=http)
    task_b = asyncio.create_task(b.run(stop))
    try:
        run = await wait_done(client, run_id)
    finally:
        stop.set()
        await task_b
    assert run["counts"]["by_outcome"] == {"passed": 1}
    ep = (await client.get(f"/v1/runs/{run_id}/episodes")).json()["items"][0]
    assert ep["attempt"] == 1  # nested work was recorded under a pending target effect
    detail = (await client.get(f"/v1/episodes/{ep['id']}")).json()
    calls = [e for e in detail["events"] if e["kind"] == "tool_call"]
    assert len(calls) == 1 and calls[0]["payload"]["via"] == "wired"
    async with state.sm() as s:
        live = (
            await s.execute(
                text("SELECT count(*) FROM effects WHERE episode_id = :e AND kind = 'tool'"),
                {"e": ep["id"]},
            )
        ).scalar()
        archived = (
            await s.execute(
                text(
                    "SELECT count(*) FROM effects_archive WHERE episode_id = :e AND kind = 'tool'"
                ),
                {"e": ep["id"]},
            )
        ).scalar()
    assert live == 1 and archived == 1
    # a token of the killed attempt is fenced off
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(state)), base_url="http://api.test"
    ) as c:
        stale = await c.post(f"/mock/{old_token}/tools/lookup_order", json={"order_id": "ord_1"})
    assert stale.status_code == 409
