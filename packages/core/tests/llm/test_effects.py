import pytest
from gauntlet_core.engine import EpisodeCtx, MemoryJournalStore, NonDeterminism, TargetError
from gauntlet_core.engine.errors import PermanentEffectError
from gauntlet_core.llm import AuthError, FakeLLM, FakeReply, llm_effect
from gauntlet_core.schema import Cost
from pydantic import BaseModel


class Out(BaseModel):
    a: int


MSGS = [{"role": "user", "content": "hi"}]


async def ctx_for(store):
    return await EpisodeCtx.open(store, "ep", run_id="r", rng_seed=1)


async def test_runs_once_and_replays_with_zero_calls():
    store = MemoryJournalStore()
    f1 = FakeLLM([FakeReply(text="hello", cost=Cost(usd_micros=5))])
    r1 = await llm_effect(await ctx_for(store), f1, "judge_small", MSGS)
    assert r1.text == "hello"
    f2 = FakeLLM([])
    r2 = await llm_effect(await ctx_for(store), f2, "judge_small", MSGS)
    assert r2.text == "hello" and r2.cost.usd_micros == 5
    assert f2.calls == []


async def test_non_retryable_error_recorded_and_replays_as_error_cls():
    store = MemoryJournalStore()
    f1 = FakeLLM([FakeReply(error=AuthError("bad key"))])
    with pytest.raises(TargetError):
        await llm_effect(await ctx_for(store), f1, "r", MSGS, error_cls=TargetError)
    f2 = FakeLLM([])
    with pytest.raises(PermanentEffectError, match="auth_error"):
        await llm_effect(await ctx_for(store), f2, "r", MSGS)
    assert f2.calls == []


async def test_parsed_model_survives_replay():
    store = MemoryJournalStore()
    f1 = FakeLLM([FakeReply(parsed={"a": 7})])
    await llm_effect(await ctx_for(store), f1, "r", MSGS, response_model=Out)
    r = await llm_effect(await ctx_for(store), FakeLLM([]), "r", MSGS, response_model=Out)
    assert r.parsed == Out(a=7)


async def test_request_change_is_nondeterminism():
    store = MemoryJournalStore()
    await llm_effect(await ctx_for(store), FakeLLM(["x"]), "r", MSGS)
    with pytest.raises(NonDeterminism):
        await llm_effect(
            await ctx_for(store), FakeLLM(["x"]), "r", [{"role": "user", "content": "other"}]
        )


async def test_cost_lands_in_ctx_spent():
    store = MemoryJournalStore()
    ctx = await ctx_for(store)
    await llm_effect(ctx, FakeLLM([FakeReply(text="x", cost=Cost(usd_micros=42))]), "r", MSGS)
    assert ctx.spent.usd_micros == 42
