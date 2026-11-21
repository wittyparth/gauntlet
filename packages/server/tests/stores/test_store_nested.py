"""Nested effects (1.7a) on every JournalStore backend: crash before every append, resume
with the abandon-attempt path, and require the journal of an uninterrupted run."""

from __future__ import annotations

from collections import Counter

import pytest
from gauntlet_core.engine import (
    EpisodeCtx,
    IndeterminateEffect,
    MemoryJournalStore,
    SimulatedCrash,
    run_episode,
)
from harness import (
    CrashingStore,
    Harness,
    NestedAgent,
    Sim,
    effect_shape,
    scenario,
    shape,
)

TURNS = ["a", "b"]


async def run_attempts(store, ep: str, calls: Counter[str]):
    """What the worker does: resume, and on IndeterminateEffect abandon and start over."""
    for _ in range(3):
        ctx = await EpisodeCtx.open(store, ep, run_id="run_c", rng_seed=7)
        try:
            return await run_episode(ctx, scenario(), NestedAgent(calls), Sim(TURNS))
        except IndeterminateEffect:
            await store.abandon_attempt(ep, ctx.epoch)
    raise AssertionError("too many attempts")


async def test_nested_spans_survive_a_crash_at_every_append(backend: Harness):
    mem = CrashingStore(MemoryJournalStore())
    await run_attempts(mem, "ep_ref", Counter())
    expected = await mem.load("ep_ref")
    assert expected.effects["target:0"].span == {
        "events": 1,
        "ordinals": {"tool": 1},
        "start": {"tool": 0},
    }
    attempts = []
    for k in range(mem.appends):
        ep = f"ep_nested_{k}"
        await backend.new_episode(ep)
        calls: Counter[str] = Counter()
        crashing = CrashingStore(backend.store, crash_before_append=k)
        with pytest.raises(SimulatedCrash):
            await run_attempts(crashing, ep, calls)
        await backend.claim(ep)  # a new worker takes the episode over
        result = await run_attempts(backend.store, ep, calls)
        j = await backend.store.load(ep)
        assert result.outcome == "passed", f"crash point {k}"
        assert shape(j.events) == shape(expected.events), f"crash point {k}"
        assert effect_shape(j) == effect_shape(expected), f"crash point {k}"
        attempts.append(j.attempt)
    assert set(attempts) == {0, 1}  # nested-window crashes abandon, the others resume
