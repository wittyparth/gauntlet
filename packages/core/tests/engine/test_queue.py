"""Memory EpisodeQueue: same lease semantics as the Postgres queue (fake clock, no sleeping)."""

import pytest
from gauntlet_core.engine import (
    EpisodeLease,
    MemoryEpisodeQueue,
    MemoryJournalStore,
    StaleLease,
)
from gauntlet_core.schema import Event


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def make():
    clock, store = Clock(), MemoryJournalStore()
    return MemoryEpisodeQueue(store, clock), store, clock


def ev(seq: int) -> Event:
    return Event.model_validate(
        {"seq": seq, "kind": "sim_note", "actor": "platform", "sim_time": "2026-01-01T00:00:00Z"}
    )


async def test_claim_orders_by_priority_then_enqueue_and_bumps_epoch():
    q, store, _ = make()
    q.enqueue("a", "r")
    q.enqueue("b", "r", priority=5)
    q.enqueue("c", "r")
    leases = await q.claim("w1", 2, 60)
    assert [x.episode_id for x in leases] == ["b", "a"]
    assert all(x.epoch == 1 and x.owner == "w1" for x in leases)
    assert (await store.load("b")).epoch == 1
    assert [x.episode_id for x in await q.claim("w2", 5, 60)] == ["c"]


async def test_expired_lease_is_reclaimed_and_old_holder_is_fenced():
    q, store, clock = make()
    q.enqueue("a", "r")
    (old,) = await q.claim("w1", 1, 60)
    await store.append("a", old.epoch, events=[ev(0)])
    assert await q.claim("w2", 1, 60) == []
    clock.t += 61
    (new,) = await q.claim("w2", 1, 60)
    assert new.epoch == old.epoch + 1
    assert await q.heartbeat(old) is False
    with pytest.raises(StaleLease):
        await store.append("a", old.epoch, events=[ev(1)])
    with pytest.raises(StaleLease):
        await q.finish(old, "passed")
    await store.append("a", new.epoch, events=[ev(1)])


async def test_heartbeat_extends_and_finish_is_final():
    q, _, clock = make()
    q.enqueue("a", "r")
    (lease,) = await q.claim("w1", 1, 60)
    clock.t += 50
    assert await q.heartbeat(lease) is True
    clock.t += 50  # 100s after claim but only 50s after the heartbeat
    assert await q.claim("w2", 1, 60) == []
    await q.finish(lease, "failed", "max_turns")
    assert (q.row("a").status, q.row("a").outcome, q.row("a").termination) == (
        "done",
        "failed",
        "max_turns",
    )
    assert await q.heartbeat(lease) is False
    clock.t += 1000
    assert await q.claim("w2", 1, 60) == []
    with pytest.raises(StaleLease):
        await q.finish(lease, "passed")


async def test_release_delays_and_not_before_is_respected():
    q, _, clock = make()
    q.enqueue("later", "r", not_before_s=100)
    q.enqueue("a", "r")
    (lease,) = await q.claim("w1", 5, 60)
    assert lease.episode_id == "a"
    await q.release(lease, retry_after_s=30)
    assert await q.claim("w2", 5, 60) == []
    clock.t += 31
    assert [x.episode_id for x in await q.claim("w2", 5, 60)] == ["a"]
    await q.release(EpisodeLease("a", "r", 1, "w1", 60), retry_after_s=0)  # stale: no-op
    assert q.row("a").status == "leased"
