"""Effect results come back with sorted keys on the live path and on replay.

Postgres `jsonb` does not keep key order, so a replayed result used to differ in key order
from the live one; serialised into a model request (`json.dumps`) that changed the request
hash and a resumed episode died with NonDeterminism (found by the chaos test)."""

from __future__ import annotations

import json

from gauntlet_core.engine import EpisodeCtx, MemoryJournalStore


async def test_live_and_replayed_results_have_the_same_key_order():
    store = MemoryJournalStore()

    async def fn():
        return {"zeta": 1, "alpha": {"y": 1, "b": [{"q": 1, "a": 2}]}, "mid": 3}, None

    live = await (await EpisodeCtx.open(store, "ep_1", run_id="r", rng_seed=1)).effect(
        "tool", {"x": 1}, fn, retry_safe=True
    )
    replayed = await (await EpisodeCtx.open(store, "ep_1", run_id="r", rng_seed=1)).effect(
        "tool", {"x": 1}, fn, retry_safe=True
    )
    assert json.dumps(live) == json.dumps(replayed)
    assert list(live) == ["alpha", "mid", "zeta"]
    assert list(live["alpha"]["b"][0]) == ["a", "q"]
