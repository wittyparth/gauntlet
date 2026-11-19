from __future__ import annotations

from collections import Counter

import pytest
from gauntlet_core.engine import (
    EpisodeCtx,
    MemoryJournalStore,
    SimTurn,
    SimulatedCrash,
    dump_cassette,
    run_episode,
    store_from_cassette,
)
from gauntlet_core.llm import FakeLLM, FakeReply, ToolCallRequest
from gauntlet_core.llm.types import ProviderUnavailable
from gauntlet_core.schema import HostedTargetConfig
from gauntlet_core.targets import HostedTarget
from gauntlet_core.world import World, build_world
from helpers import SPEC, scenario

CFG = HostedTargetConfig(model="openrouter/deepseek/deepseek-v4-flash", system_prompt="Be nice.")


class Turns:
    def __init__(self, *texts: str) -> None:
        self.texts = list(texts)

    async def next_message(self, ctx: EpisodeCtx) -> SimTurn:
        n = sum(1 for e in ctx.trajectory_so_far if e.kind == "user_message")
        return SimTurn("message", self.texts[n]) if n < len(self.texts) else SimTurn("done")


def tc(name: str, args: dict, id: str = "t1") -> FakeReply:
    return FakeReply(tool_calls=[ToolCallRequest(id, name, args)])


async def run(llm, cfg=CFG, store=None, sim=None, rounds=8):
    store = store or MemoryJournalStore()
    ctx = await EpisodeCtx.open(store, "ep", run_id="r", rng_seed=7)
    world = World(build_world(SPEC, None, 7))
    ctx.state["world"] = world
    target = HostedTarget(cfg, world, llm, max_tool_rounds=rounds)
    res = await run_episode(ctx, scenario(), target, sim or Turns("where is it?"))
    return res, store, ctx


async def test_plain_reply():
    llm = FakeLLM(["It will ship."])
    res, store, _ = await run(llm)
    events = (await store.load("ep")).events
    assert [e.payload["text"] for e in events if e.kind == "agent_message"] == ["It will ship."]
    assert llm.calls[0].role == f"model:{CFG.model}"
    assert res.outcome == "passed"


async def test_tool_call_goes_through_world_with_via_hosted():
    llm = FakeLLM([tc("lookup_order", {"order_id": "ord_1"}), "It shipped."])
    _, store, _ = await run(llm)
    events = (await store.load("ep")).events
    call = next(e for e in events if e.kind == "tool_call")
    assert call.payload["via"] == "hosted" and call.payload["tool"] == "lookup_order"
    result = next(e for e in events if e.kind == "tool_result")
    assert result.payload["result"]["status"] == "shipped"
    second = llm.calls[1].messages
    assert second[-1]["role"] == "tool" and second[-1]["tool_call_id"] == "t1"
    assert second[-2]["role"] == "assistant" and second[-2]["tool_calls"][0]["id"] == "t1"


async def test_two_tool_rounds_then_text():
    llm = FakeLLM(
        [
            tc("lookup_order", {"order_id": "ord_1"}, "a"),
            tc("lookup_order", {"order_id": "ord_2"}, "b"),
            "done",
        ]
    )
    _, store, _ = await run(llm)
    events = (await store.load("ep")).events
    assert sum(1 for e in events if e.kind == "tool_call") == 2
    assert len(llm.calls) == 3


async def test_tool_subset_enforced():
    cfg = CFG.model_copy(update={"tools": ["lookup_order"]})
    llm = FakeLLM([tc("cancel_order", {"order_id": "ord_1"}), "ok"])
    _, store, _ = await run(llm, cfg)
    events = (await store.load("ep")).events
    assert not any(e.kind == "tool_call" for e in events)
    assert '"unknown_tool"' in llm.calls[1].messages[-1]["content"]
    assert [t["function"]["name"] for t in llm.calls[0].tools or []] == ["lookup_order"]


async def test_bad_arguments_return_tool_error_and_model_recovers():
    llm = FakeLLM(
        [
            tc("lookup_order", {"_raw": "{oops"}, "a"),
            tc("lookup_order", {"order_id": "ord_1"}, "b"),
            "shipped",
        ]
    )
    _, store, _ = await run(llm)
    results = [e for e in (await store.load("ep")).events if e.kind == "tool_result"]
    assert results[0].payload["ok"] is False and "invalid_args" in results[0].payload["error"]
    assert results[1].payload["ok"] is True
    assert "invalid_args" in llm.calls[1].messages[-1]["content"]


async def test_system_context_canary_in_system_message():
    llm = FakeLLM(["hi"])
    await run(llm)
    system = llm.calls[0].messages[0]["content"]
    assert system.startswith("Be nice.") and "ops key:" in system


async def test_round_limit_forces_text_answer_without_tools():
    script: list = [tc("lookup_order", {"order_id": "ord_1"}, "a")] * 2 + ["final"]
    llm = FakeLLM(script)
    _, store, _ = await run(llm, rounds=2)
    assert llm.calls[-1].tools is None
    events = (await store.load("ep")).events
    assert any(e.kind == "agent_message" and e.payload["text"] == "final" for e in events)


async def test_llm_failure_ends_target_error():
    llm = FakeLLM([FakeReply(error=ProviderUnavailable("down"))])
    res, _, _ = await run(llm)
    assert (res.outcome, res.termination) == ("target_error", "target_unreachable")


async def test_resume_after_crash_converges_on_identical_journal():
    script: list = [tc("lookup_order", {"order_id": "ord_1"}), "It shipped."]
    _, clean_store, _ = await run(FakeLLM(script))
    expected = [(e.kind, e.payload) for e in (await clean_store.load("ep")).events]
    for k in range(clean_store.appends):
        # the resumed run's script is consumed only by calls that were not recorded
        store = MemoryJournalStore()
        store.crash_before_append = k
        first = FakeLLM(script)
        with pytest.raises(SimulatedCrash):
            await run(first, store=store)
        recorded = sum(
            1
            for r in (await store.load("ep")).effects.values()
            if r.kind == "llm" and r.status == "done"
        )
        store.crash_before_append = None
        store.bump_epoch("ep")
        second = FakeLLM(script[recorded:])
        await run(second, store=store)
        events = (await store.load("ep")).events
        assert [(e.kind, e.payload) for e in events] == expected, k
        assert len(second.calls) == len(script) - recorded


async def test_strict_cassette_replay_makes_zero_calls():
    llm = FakeLLM([tc("lookup_order", {"order_id": "ord_1"}), "It shipped."])
    _, store, _ = await run(llm)
    text = dump_cassette(await store.load("ep"))
    replay_store = await store_from_cassette(text, "ep")
    silent = FakeLLM([])
    ctx = await EpisodeCtx.open(replay_store, "ep", run_id="r", rng_seed=7, replay_only=True)
    world = World(build_world(SPEC, None, 7))
    ctx.state["world"] = world
    await run_episode(ctx, scenario(), HostedTarget(CFG, world, silent), Turns("where is it?"))
    assert silent.calls == []
    assert Counter(e.kind for e in (await replay_store.load("ep")).events)["tool_call"] == 1
