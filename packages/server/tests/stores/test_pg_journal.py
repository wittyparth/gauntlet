"""Postgres-only journal behaviour: concurrency, cost accounting, atomicity, attempt archive.
The shared contract lives in test_store_contract.py."""

from __future__ import annotations

import asyncio

import pytest
from gauntlet_core.engine import SeqConflict, StaleLease
from gauntlet_server.db import Sessionmaker
from gauntlet_server.stores import PgJournalStore, journal
from harness import effect, event
from pg_helpers import add_episode, add_run, one, scalar
from sqlalchemy import text

pytestmark = pytest.mark.integration

EP = "ep_1"


@pytest.fixture
async def store(sm: Sessionmaker) -> PgJournalStore:
    await add_run(sm)
    await add_episode(sm, EP)
    return PgJournalStore(sm)


async def test_concurrent_appends_of_the_same_seq_one_wins(store: PgJournalStore):
    results = await asyncio.gather(
        *(store.append(EP, 0, events=[event(0)]) for _ in range(8)), return_exceptions=True
    )
    assert sum(r is None for r in results) == 1
    assert all(isinstance(r, SeqConflict) for r in results if r is not None)
    assert len((await store.load(EP)).events) == 1


async def test_concurrent_appends_serialise_into_dense_seqs(store: PgJournalStore):
    async def writer(i: int) -> None:
        while True:
            n = len((await store.load(EP)).events)
            try:
                await store.append(EP, 0, events=[event(n, text=f"w{i}")])
                return
            except SeqConflict:
                continue

    await asyncio.gather(*(writer(i) for i in range(6)))
    assert [e.seq for e in (await store.load(EP)).events] == list(range(6))


async def test_cost_counted_once_even_if_done_is_appended_twice(
    store: PgJournalStore, sm: Sessionmaker
):
    await store.append(EP, 0, effects=[effect("llm:0", "pending")])
    await store.append(EP, 0, effects=[effect("llm:0", "done", cost=40)])
    await store.append(EP, 0, effects=[effect("llm:0", "done", cost=40), effect("llm:1", cost=2)])
    assert await scalar(sm, "SELECT cost_usd_micros FROM episodes WHERE id = :i", i=EP) == 42
    assert await scalar(sm, "SELECT count(*) FROM effects WHERE episode_id = :i", i=EP) == 2


async def test_failure_mid_transaction_leaves_no_events(
    store: PgJournalStore, sm: Sessionmaker, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(journal, "_UPSERT_EFFECT", text("SELECT 1/0"))
    with pytest.raises(Exception, match="division by zero"):
        await store.append(EP, 0, events=[event(0)], effects=[effect("llm:0")])
    row = await one(sm, "SELECT next_seq FROM episodes WHERE id = :i", i=EP)
    assert row[0] == 0
    assert await scalar(sm, "SELECT count(*) FROM events") == 0


async def test_unknown_episode_is_stale_on_append_and_empty_on_load(store: PgJournalStore):
    j = await store.load("ep_missing")
    assert j.events == [] and j.epoch == 0
    with pytest.raises(StaleLease):
        await store.append("ep_missing", 0, events=[event(0)])


async def test_abandon_attempt_archives_and_restarts(store: PgJournalStore, sm: Sessionmaker):
    await store.append(
        EP, 0, events=[event(0), event(1)], effects=[effect("llm:0", cost=9), effect("target:0")]
    )
    with pytest.raises(StaleLease):
        await store.abandon_attempt(EP, 5)
    assert await store.abandon_attempt(EP, 0) == 1
    j = await store.load(EP)
    assert j.events == [] and j.effects == {}
    assert await scalar(sm, "SELECT next_seq FROM episodes WHERE id = :i", i=EP) == 0
    assert await scalar(sm, "SELECT count(*) FROM events_archive WHERE attempt = 0") == 2
    assert await scalar(sm, "SELECT count(*) FROM effects_archive WHERE attempt = 0") == 2
    await store.append(EP, 0, events=[event(0)], effects=[effect("llm:0")])  # fresh attempt
    assert [e.seq for e in (await store.load(EP)).events] == [0]
