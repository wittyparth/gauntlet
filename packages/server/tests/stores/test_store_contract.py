"""One contract suite for every JournalStore: Memory, SQLite and Postgres (integration).

The last tests re-run the engine's resume-from-every-crash-point scenario on each backend
and require the journal to equal the one an uninterrupted in-memory run produces.
"""

from __future__ import annotations

from collections import Counter

import pytest
from gauntlet_core.engine import (
    EpisodeCtx,
    MemoryJournalStore,
    SeqConflict,
    SimulatedCrash,
    StaleLease,
    run_episode,
)
from harness import (
    Agent,
    CrashingStore,
    Harness,
    Sim,
    effect,
    effect_shape,
    event,
    scenario,
    shape,
)

EP = "ep_1"
TURNS = ["a", "b", "c"]


async def test_append_load_round_trip(backend: Harness):
    await backend.new_episode(EP)
    evs = [event(0, "episode_started", x=1), event(1), event(2, text="héllo ✓")]
    fx = [effect("llm:0", result={"text": "hi"}, cost=7), effect("target:0", "pending")]
    await backend.store.append(EP, 0, events=evs, effects=fx)
    j = await backend.store.load(EP)
    assert j.events == evs
    assert j.effects == {e.key: e for e in fx}
    assert j.epoch == 0
    await backend.store.append(EP, 0, events=[event(3)])
    assert [e.seq for e in (await backend.store.load(EP)).events] == [0, 1, 2, 3]


async def test_load_reports_the_current_epoch(backend: Harness):
    await backend.new_episode(EP)
    assert await backend.claim(EP) == 1
    assert (await backend.store.load(EP)).epoch == 1


async def test_stale_epoch_raises_and_writes_nothing(backend: Harness):
    await backend.new_episode(EP)
    await backend.claim(EP)
    with pytest.raises(StaleLease):
        await backend.store.append(EP, 0, events=[event(0)], effects=[effect("llm:0")])
    j = await backend.store.load(EP)
    assert j.events == [] and j.effects == {}  # neither events nor the effect upsert landed
    await backend.store.append(EP, 1, events=[event(0)], effects=[effect("llm:0")])
    assert len((await backend.store.load(EP)).events) == 1


@pytest.mark.parametrize("seqs", [[0], [3, 4], [2, 4]], ids=["duplicate", "gap", "not dense"])
async def test_bad_seq_raises_and_writes_nothing(backend: Harness, seqs: list[int]):
    await backend.new_episode(EP)
    await backend.store.append(EP, 0, events=[event(0), event(1)])
    with pytest.raises(SeqConflict):
        await backend.store.append(
            EP, 0, events=[event(s) for s in seqs], effects=[effect("llm:0")]
        )
    j = await backend.store.load(EP)
    assert [e.seq for e in j.events] == [0, 1] and j.effects == {}


async def test_effect_upsert_and_no_regression(backend: Harness):
    await backend.new_episode(EP)
    await backend.store.append(EP, 0, effects=[effect("target:0", "pending")])
    assert (await backend.store.load(EP)).effects["target:0"].status == "pending"
    done = effect("target:0", "done", reply="r")
    await backend.store.append(EP, 0, events=[event(0)], effects=[done])
    j = await backend.store.load(EP)
    assert j.effects == {"target:0": done}
    await backend.store.append(EP, 0, effects=[effect("target:0", "pending")])
    assert (await backend.store.load(EP)).effects == {"target:0": done}


async def test_unrelated_episodes_do_not_interfere(backend: Harness):
    await backend.new_episode("ep_a")
    await backend.new_episode("ep_b")
    await backend.store.append("ep_a", 0, events=[event(0)], effects=[effect("llm:0")])
    b = await backend.store.load("ep_b")
    assert b.events == [] and b.effects == {}
    await backend.store.append("ep_b", 0, events=[event(0)])


async def test_effect_span_round_trips(backend: Harness):
    await backend.new_episode(EP)
    rec = effect("target:0", "done", reply="r").model_copy(
        update={"span": {"events": 2, "ordinals": {"tool": 1}}}
    )
    await backend.store.append(EP, 0, events=[event(0), event(1)], effects=[rec])
    assert (await backend.store.load(EP)).effects["target:0"].span == rec.span


async def test_abandon_attempt_resets_the_journal_and_counts_attempts(backend: Harness):
    await backend.new_episode(EP)
    epoch = await backend.claim(EP)
    await backend.store.append(
        EP, epoch, events=[event(0), event(1)], effects=[effect("llm:0", cost=4)]
    )
    assert (await backend.store.load(EP)).attempt == 0
    assert await backend.store.abandon_attempt(EP, epoch) == 1
    j = await backend.store.load(EP)
    assert (j.events, j.effects, j.attempt, j.epoch) == ([], {}, 1, epoch)
    await backend.store.append(EP, epoch, events=[event(0)], effects=[effect("llm:0")])
    assert [e.seq for e in (await backend.store.load(EP)).events] == [0]
    assert await backend.store.abandon_attempt(EP, epoch) == 2
    with pytest.raises(StaleLease):
        await backend.store.abandon_attempt(EP, epoch + 1)


# ------------------------------------------------------------- engine on every backend


async def run(store, episode_id: str, calls: Counter[str] | None = None):
    ctx = await EpisodeCtx.open(store, episode_id, run_id="run_c", rng_seed=7)
    return await run_episode(ctx, scenario(), Agent(calls or Counter()), Sim(TURNS))


async def reference():
    mem = CrashingStore(MemoryJournalStore())
    await run(mem, EP)
    return mem, await mem.load(EP)


async def test_engine_journal_matches_memory_reference(backend: Harness):
    _, expected = await reference()
    await backend.new_episode(EP)
    result = await run(backend.store, EP)
    j = await backend.store.load(EP)
    assert result.outcome == "passed"
    assert shape(j.events) == shape(expected.events)
    assert effect_shape(j) == effect_shape(expected)


async def test_resume_from_every_crash_point_converges(backend: Harness):
    clean, expected = await reference()
    for k in range(clean.appends):
        ep = f"ep_crash_{k}"
        await backend.new_episode(ep)
        calls: Counter[str] = Counter()
        crashing = CrashingStore(backend.store, crash_before_append=k)
        with pytest.raises(SimulatedCrash):
            await run(crashing, ep, calls)
        await backend.claim(ep)  # a new worker takes the episode over
        result = await run(backend.store, ep, calls)
        j = await backend.store.load(ep)
        assert result.outcome == "passed", f"crash point {k}"
        assert shape(j.events) == shape(expected.events), f"crash point {k}"
        assert effect_shape(j) == effect_shape(expected), f"crash point {k}"
        assert all(r.status == "done" for r in j.effects.values())
        assert (
            max(calls.values(), default=0) <= 2
        )  # a target call runs twice only if the crash caught it


async def test_zombie_worker_is_fenced_off(backend: Harness):
    await backend.new_episode(EP)
    ctx = await EpisodeCtx.open(backend.store, EP, run_id="run_c", rng_seed=7)
    await backend.claim(EP)  # lease expired, someone else owns it
    with pytest.raises(StaleLease):
        await run_episode(ctx, scenario(), Agent(Counter()), Sim(TURNS))
    assert (await backend.store.load(EP)).events == []
