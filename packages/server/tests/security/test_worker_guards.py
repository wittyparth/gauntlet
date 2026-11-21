"""Worker guards: ownership re-check at claim time and the per-host traffic limits."""

from __future__ import annotations

import asyncio
import itertools
import time

import httpx
import pytest
from atk_helpers import make_turn_suite, make_version, run_body
from gauntlet_server.limits import HostLimiter, LimitedTransport
from gauntlet_server.worker import Worker
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def test_unverified_remote_at_claim_time_ends_platform_error(client, state):
    version = await make_version(client, "https://agent.victim.com/v1")
    suite = await make_turn_suite(client, state)
    async with state.sm() as s, s.begin():  # a record that lapses after run creation
        await s.execute(
            text(
                "INSERT INTO target_verifications (id, workspace_id, host, method, token, status, "
                "expires_at) VALUES ('tvf_1', 'ws_test', 'victim.com', 'dns', 't', 'verified', "
                "now() + interval '1 day')"
            )
        )
    run_id = (await client.post("/v1/runs", json=run_body(suite, version))).json()["id"]
    async with state.sm() as s, s.begin():
        await s.execute(text("DELETE FROM target_verifications"))
    calls: list[httpx.Request] = []

    async def agent(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={})

    http = httpx.AsyncClient(transport=httpx.MockTransport(agent))
    worker = Worker(state, concurrency=1, poll_interval_s=0.05, http=http)
    stop = asyncio.Event()
    task = asyncio.create_task(worker.run(stop))
    ep: dict = {}
    try:
        for _ in range(100):
            ep = (await client.get(f"/v1/runs/{run_id}/episodes")).json()["items"][0]
            if ep["status"] == "done":
                break
            await asyncio.sleep(0.1)
    finally:
        stop.set()
        await asyncio.wait_for(task, 10)
    assert ep["outcome"] == "platform_error" and calls == []
    detail = (await client.get(f"/v1/episodes/{ep['id']}")).json()
    ended = [e for e in detail["events"] if e["kind"] == "episode_ended"][-1]
    assert ended["payload"]["detail"] == "target_not_verified"
    assert (await client.get(f"/v1/runs/{run_id}")).json()["status"] == "cancelled"


async def test_host_semaphore_limits_concurrency_to_two_and_spaces_requests(state):
    limiter = HostLimiter(state.redis, max_concurrent=2, min_gap_s=0.05)
    active = peak = 0
    starts: list[float] = []

    class Inner(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            starts.append(time.monotonic())
            await asyncio.sleep(0.15)
            active -= 1
            return httpx.Response(200, json={})

    client = httpx.AsyncClient(transport=LimitedTransport(Inner(), limiter, {"dva"}))
    await asyncio.gather(*(client.get("https://remote.example.com/x") for _ in range(6)))
    assert peak == 2
    ordered = sorted(starts)
    assert min(b - a for a, b in itertools.pairwise(ordered)) >= 0.04
    assert await state.redis.get("gauntlet:hostsem:remote.example.com") in (b"0", None)
    peak = 0  # local hosts bypass the limiter entirely
    await asyncio.gather(*(client.get("http://dva:8100/x") for _ in range(4)))
    assert peak == 4
