"""agent_live replay: engine-level cases that need no particular store backend."""

from collections import Counter
from typing import Any

import pytest
from gauntlet_core.engine import (
    EpisodeCtx,
    MemoryJournalStore,
    NonDeterminism,
    SimTurn,
    run_episode,
)
from gauntlet_core.engine.replay import nested_keys
from gauntlet_core.schema import Cost, EffectRecord

from .test_engine import Agent, Sim, scenario


def rec(key: str, **kw) -> EffectRecord:
    kind: Any = key.split(":")[0]
    return EffectRecord(key=key, kind=kind, request_hash="h", status="done", result={}, **kw)


def test_nested_keys_come_from_target_spans():
    effects = {
        "llm:0": rec("llm:0"),  # sim, turn 0
        "target:0": rec("target:0", span={"events": 3, "ordinals": {"llm": 2, "tool": 1}}),
        "llm:1": rec("llm:1"),
        "llm:2": rec("llm:2"),  # nested in target:0
        "tool:0": rec("tool:0"),
        "llm:3": rec("llm:3"),  # sim, turn 1
        "target:1": rec("target:1", span={"events": 1, "ordinals": {"llm": 1}}),
        "llm:4": rec("llm:4"),  # nested in target:1
    }
    assert nested_keys(effects) == {"llm:1", "llm:2", "tool:0", "llm:4"}


async def test_agent_live_over_an_empty_journal_is_plain_live():
    store = MemoryJournalStore()
    calls: Counter = Counter()
    ctx = await EpisodeCtx.open(store, "ep", run_id="r", rng_seed=1, mode="agent_live")
    res = await run_episode(ctx, scenario(), Agent(calls), Sim(["a", "b"], calls))
    j = await store.load("ep")
    assert res.outcome == "passed" and calls["sim:0"] == 1
    assert not ctx.diverged and not any(e.kind == "sim_note" for e in j.events)


async def test_strict_mode_still_raises_on_a_changed_request():
    calls: Counter = Counter()
    store = MemoryJournalStore()
    ctx = await EpisodeCtx.open(store, "ep", run_id="r", rng_seed=1)
    await run_episode(ctx, scenario(), Agent(calls), Sim(["a"], calls))

    class Other(Sim):
        async def next_message(self, ctx):
            async def fn():
                return {"text": "a"}, Cost()

            await ctx.effect("llm", {"changed": True}, fn, retry_safe=True)
            return SimTurn("done")

    ctx2 = await EpisodeCtx.open(store, "ep", run_id="r", rng_seed=1, replay_only=True)
    with pytest.raises(NonDeterminism):
        await run_episode(ctx2, scenario(), Agent(calls), Other([], calls))
    assert ctx2.mode == "strict"


async def test_fork_uses_recorded_span_starts_when_the_simulator_makes_extra_calls():
    """A structured-repair call before the simulator's turn call makes the loop-shape inference
    wrong; the recorded `start` ordinals keep exactly the simulator's effects."""
    from gauntlet_core.engine import fork_for_agent_live

    async def const():
        return {"text": "x"}, Cost()

    nested: list[str] = []

    class RepairSim(Sim):
        async def next_message(self, ctx):
            n = sum(1 for e in ctx.trajectory_so_far if e.kind == "user_message")
            await ctx.effect("llm", {"repair": n}, const, retry_safe=True)  # the extra call
            return await super().next_message(ctx)

    class NestingAgent(Agent):
        async def send(self, ctx, user_text):
            async def fn():
                nested.append(f"llm:{ctx._ordinals.get('llm', 0)}")  # key of the call below
                await ctx.effect("llm", {"nested": user_text}, const, retry_safe=True)
                return {"reply": f"re: {user_text}"}, None

            res = await ctx.effect("target", {"text": user_text}, fn, retry_safe=True)
            return res["reply"]

    store = MemoryJournalStore()
    calls: Counter = Counter()
    ctx = await EpisodeCtx.open(store, "src", run_id="r", rng_seed=1)
    await run_episode(ctx, scenario(), NestingAgent(calls), RepairSim(["a", "b"], calls))
    snap = await store.load("src")
    assert len(nested) == 2 and all(
        r.span for k, r in snap.effects.items() if k.startswith("target")
    )
    assert nested_keys(snap.effects) == set(nested)

    # the same journal with the starts stripped (an older recording) falls back to inference,
    # which the extra calls throw off: this is what recording `start` fixes
    stripped = {
        k: r.model_copy(
            update={"span": {n: v for n, v in r.span.items() if n != "start"} if r.span else None}
        )
        for k, r in snap.effects.items()
    }
    assert nested_keys(stripped) != set(nested)

    await fork_for_agent_live(store, "src", "fork")
    forked = await store.load("fork")
    sim_keys = {k for k, r in snap.effects.items() if r.kind == "llm"} - set(nested)
    assert set(forked.effects) == sim_keys and len(sim_keys) == 6  # 3 turns x (repair + turn)
    assert not any(k.startswith("target") for k in forked.effects)
