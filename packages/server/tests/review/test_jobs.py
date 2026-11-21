"""The Postgres job queue: leases, attempts, handler results, the status route."""

from __future__ import annotations

import asyncio

import pytest
from gauntlet_server.services.jobs import JOB_HANDLERS, handler, run_job
from gauntlet_server.stores.jobs import MAX_ATTEMPTS, PgJobQueue
from pg_helpers import execute, one

pytestmark = pytest.mark.integration


async def test_enqueue_and_concurrent_claims_are_disjoint(sm):
    q = PgJobQueue(sm)
    ids = {await q.enqueue("ws_test", "noop", {"i": i}) for i in range(6)}
    a, b = await asyncio.gather(q.claim("w1", 4, 30), q.claim("w2", 4, 30))
    got = [lease.id for lease in a + b]
    assert len(got) == len(set(got)) == 6 and set(got) == ids
    assert await q.claim("w3", 4, 30) == []


async def test_lease_expiry_reclaims_and_three_attempts_then_failed(sm):
    q = PgJobQueue(sm)
    jid = await q.enqueue("ws_test", "noop", {})
    for attempt in range(1, MAX_ATTEMPTS + 1):
        (lease,) = await q.claim(f"w{attempt}", 1, 30)
        assert lease.attempts == attempt
        assert await q.claim("other", 1, 30) == []  # leased: nobody else gets it
        await execute(sm, "UPDATE jobs SET lease_expires_at = now() - interval '1 second'")
    assert await q.claim("late", 1, 30) == []  # out of attempts
    row = await one(sm, "SELECT status, error FROM jobs WHERE id = :i", i=jid)
    assert row.status == "failed" and "lease expired" in row.error


async def test_fail_retries_then_gives_up(sm):
    q = PgJobQueue(sm)
    jid = await q.enqueue("ws_test", "noop", {})
    for n in range(1, MAX_ATTEMPTS + 1):
        (lease,) = await q.claim("w", 1, 30)
        assert await q.fail(lease, "boom")
        row = await one(sm, "SELECT status FROM jobs WHERE id = :i", i=jid)
        assert row.status == ("failed" if n == MAX_ATTEMPTS else "queued")


async def test_a_stale_owner_cannot_complete(sm):
    q = PgJobQueue(sm)
    await q.enqueue("ws_test", "noop", {})
    (lease,) = await q.claim("w1", 1, 30)
    await execute(sm, "UPDATE jobs SET lease_expires_at = now() - interval '1 second'")
    (lease2,) = await q.claim("w2", 1, 30)
    assert not await q.complete(lease, {"x": 1})
    assert await q.complete(lease2, {"x": 2})


async def test_handler_result_is_stored_and_visible_through_the_route(client, state):
    @handler("echo")
    async def echo(ctx):
        return {"got": ctx.payload["v"], "attempt": ctx.attempts}

    @handler("explode")
    async def explode(ctx):
        raise RuntimeError("nope")

    try:
        q = PgJobQueue(state.sm)
        ok = await q.enqueue("ws_test", "echo", {"v": 7})
        bad = await q.enqueue("ws_test", "explode", {})
        for lease in await q.claim("w", 5, 30):
            await run_job(state, q, lease)
        r = (await client.get(f"/v1/jobs/{ok}")).json()
        assert r["status"] == "done" and r["result"] == {"got": 7, "attempt": 1}
        r = (await client.get(f"/v1/jobs/{bad}")).json()
        assert r["status"] == "queued" and "RuntimeError: nope" in r["error"]
        assert (await client.get("/v1/jobs/job_missing")).status_code == 404
    finally:
        JOB_HANDLERS.pop("echo", None)
        JOB_HANDLERS.pop("explode", None)
