from __future__ import annotations

import asyncio

import pytest
from gauntlet_core.engine import EpisodeLease, StaleLease
from gauntlet_server.db import Sessionmaker
from gauntlet_server.stores import PgEpisodeQueue, PgJournalStore
from harness import event
from pg_helpers import add_episode, add_run, execute, one, scalar

pytestmark = pytest.mark.integration


@pytest.fixture
async def q(sm: Sessionmaker) -> PgEpisodeQueue:
    await add_run(sm)
    return PgEpisodeQueue(sm)


async def expire(sm: Sessionmaker, episode_id: str) -> None:
    await execute(
        sm,
        "UPDATE episodes SET lease_expires_at = now() - interval '5 seconds' WHERE id = :i",
        i=episode_id,
    )


async def test_claim_respects_limit_priority_and_created_at(sm, q):
    await add_episode(sm, "a", priority=0, created_at_offset_s=-30)
    await add_episode(sm, "b", priority=5, created_at_offset_s=-10)
    await add_episode(sm, "c", priority=0, created_at_offset_s=-20)
    await add_episode(sm, "d", priority=5, created_at_offset_s=-20)
    leases = await q.claim("w1", 3, 60)
    assert [x.episode_id for x in leases] == ["d", "b", "a"]
    assert await q.claim("w2", 0, 60) == []


async def test_claim_sets_epoch_status_started_at_and_run_running(sm, q):
    await add_episode(sm, "a")
    (lease,) = await q.claim("w1", 5, 60)
    assert (lease.epoch, lease.owner, lease.run_id, lease.lease_s) == (1, "w1", "run_1", 60)
    row = await one(
        sm,
        "SELECT status, lease_owner, epoch, started_at IS NOT NULL, "
        "lease_expires_at > now() + interval '55 seconds' FROM episodes WHERE id='a'",
    )
    assert tuple(row) == ("leased", "w1", 1, True, True)
    assert await scalar(sm, "SELECT status FROM runs WHERE id='run_1'") == "running"
    assert await q.claim("w2", 5, 60) == []  # a live lease is not claimable


async def test_concurrent_claimers_get_disjoint_sets_covering_all(sm, q):
    for i in range(50):
        await add_episode(sm, f"e{i:02}", created_at_offset_s=i)
    queues = [PgEpisodeQueue(sm) for _ in range(8)]

    async def drain(n: int) -> list[EpisodeLease]:
        got: list[EpisodeLease] = []
        while batch := await queues[n].claim(f"w{n}", 3, 60):
            got += batch
        return got

    results = await asyncio.gather(*(drain(n) for n in range(8)))
    ids = [x.episode_id for r in results for x in r]
    assert len(ids) == len(set(ids)) == 50
    assert sum(1 for r in results if r) > 1  # the work really was shared
    assert {x.epoch for r in results for x in r} == {1}


async def test_single_round_of_parallel_claims_never_overlaps(sm, q):
    for i in range(10):
        await add_episode(sm, f"e{i}")
    results = await asyncio.gather(*(PgEpisodeQueue(sm).claim(f"w{n}", 5, 60) for n in range(4)))
    ids = [x.episode_id for r in results for x in r]
    assert len(ids) == len(set(ids)) and len(ids) <= 10


async def test_expired_lease_is_reclaimed_with_bumped_epoch(sm, q):
    await add_episode(sm, "a")
    (first,) = await q.claim("w1", 1, 60)
    assert await q.claim("w2", 1, 60) == []
    await expire(sm, "a")
    (second,) = await q.claim("w2", 1, 60)
    assert (second.episode_id, second.epoch, second.owner) == ("a", first.epoch + 1, "w2")


async def test_zombie_holder_is_fenced_everywhere(sm, q):
    await add_episode(sm, "a")
    (old,) = await q.claim("w1", 1, 60)
    await PgJournalStore(sm).append("a", old.epoch, events=[event(0)])
    await expire(sm, "a")
    (new,) = await q.claim("w2", 1, 60)
    assert await q.heartbeat(old) is False
    with pytest.raises(StaleLease):
        await PgJournalStore(sm).append("a", old.epoch, events=[event(1)])
    with pytest.raises(StaleLease):
        await q.finish(old, "passed")
    await q.release(old, retry_after_s=0)  # no-op for a lost lease
    assert await scalar(sm, "SELECT lease_owner FROM episodes WHERE id='a'") == "w2"
    assert await q.heartbeat(new) is True
    await PgJournalStore(sm).append("a", new.epoch, events=[event(1)])


async def test_heartbeat_extends_the_lease(sm, q):
    await add_episode(sm, "a")
    (lease,) = await q.claim("w1", 1, 60)
    await execute(sm, "UPDATE episodes SET lease_expires_at = now() + interval '1 second'")
    assert await q.heartbeat(lease) is True
    assert await scalar(sm, "SELECT lease_expires_at > now() + interval '55 seconds' FROM episodes")


async def test_finish_marks_done_and_is_not_claimable_again(sm, q):
    await add_episode(sm, "a")
    (lease,) = await q.claim("w1", 1, 60)
    await q.finish(lease, "failed", "max_turns")
    row = await one(
        sm,
        "SELECT status, outcome, termination, lease_owner, finished_at IS NOT NULL FROM episodes",
    )
    assert tuple(row) == ("done", "failed", "max_turns", None, True)
    assert await q.heartbeat(lease) is False
    await expire(sm, "a")
    assert await q.claim("w2", 1, 60) == []
    with pytest.raises(StaleLease):
        await q.finish(lease, "passed")  # finishing twice


async def test_not_before_is_respected(sm, q):
    await add_episode(sm, "later", not_before_offset_s=3600)
    await add_episode(sm, "now")
    assert [x.episode_id for x in await q.claim("w1", 5, 60)] == ["now"]


async def test_release_requeues_after_the_delay(sm, q):
    await add_episode(sm, "a")
    (lease,) = await q.claim("w1", 1, 60)
    await q.release(lease, retry_after_s=3600)
    row = await one(sm, "SELECT status, lease_owner, not_before > now() FROM episodes")
    assert tuple(row) == ("queued", None, True)
    assert await q.claim("w2", 1, 60) == []
    await execute(sm, "UPDATE episodes SET not_before = now() - interval '1 second'")
    (again,) = await q.claim("w2", 1, 60)
    assert again.epoch == lease.epoch + 1


async def test_release_with_zero_delay_is_immediately_claimable(sm, q):
    await add_episode(sm, "a")
    (lease,) = await q.claim("w1", 1, 60)
    await q.release(lease, retry_after_s=0)
    assert len(await q.claim("w2", 1, 60)) == 1


@pytest.mark.parametrize("status", ["paused", "cancelled", "done"])
async def test_inactive_runs_are_not_claimed(sm, q, status):
    await add_run(sm, "run_x", status=status)
    await add_episode(sm, "x", "run_x")
    assert await q.claim("w1", 5, 60) == []
    await execute(sm, "UPDATE runs SET status = 'running' WHERE id = 'run_x'")
    assert len(await q.claim("w1", 5, 60)) == 1


async def test_lease_times_come_from_the_database_clock(sm, q):
    """now() is evaluated by Postgres: leases written by two 'workers' are comparable
    without any Python-side clock being involved."""
    await add_episode(sm, "a")
    (lease,) = await q.claim("w1", 1, 5)
    delta = await scalar(sm, "SELECT extract(epoch FROM lease_expires_at - now()) FROM episodes")
    assert 0 < float(delta) <= 5 and lease.lease_s == 5
