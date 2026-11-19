from __future__ import annotations

import pytest
from gauntlet_core.engine import EpisodeCtx, MemoryJournalStore, PermanentEffectError
from gauntlet_core.llm import (
    FakeLLM,
    FakeReply,
    extract_json_object,
    lenient_json,
    structured_call,
    structured_effect,
)
from gauntlet_core.llm.structured import repair_messages
from pydantic import BaseModel


class Out(BaseModel):
    a: int


MSGS = [{"role": "user", "content": "go"}]


async def ctx_for(store=None):
    return await EpisodeCtx.open(store or MemoryJournalStore(), "ep", run_id="r", rng_seed=1)


async def test_valid_first_call_is_one_call():
    llm = FakeLLM(['{"a": 1}'])
    r = await structured_effect(await ctx_for(), llm, "r", MSGS, response_model=Out)
    assert r.parsed == Out(a=1) and len(llm.calls) == 1


async def test_repair_retry_sends_error_and_bad_reply_back():
    llm = FakeLLM(['{"a": "x"', '{"a": 2}'])
    r = await structured_effect(await ctx_for(), llm, "r", MSGS, response_model=Out)
    assert r.parsed == Out(a=2) and len(llm.calls) == 2
    second = llm.calls[1].messages
    assert second[:1] == MSGS
    assert second[1] == {"role": "assistant", "content": '{"a": "x"'}
    assert "could not be used" in second[2]["content"] and "JSON" in second[2]["content"]


async def test_empty_reply_repair_has_no_empty_assistant_turn():
    llm = FakeLLM(["", '{"a": 3}'])
    r = await structured_effect(await ctx_for(), llm, "r", MSGS, response_model=Out)
    assert r.parsed == Out(a=3)
    assert [m["role"] for m in llm.calls[1].messages] == ["user", "user"]


async def test_lenient_fallback_after_two_failures_extracts_fenced_json():
    fenced = 'Sure!\n```json\n{"a": 7}\n```'
    llm = FakeLLM(["nope", fenced])
    r = await structured_effect(
        await ctx_for(), llm, "r", MSGS, response_model=Out, lenient=lenient_json(Out)
    )
    assert r.parsed == Out(a=7) and len(llm.calls) == 2


async def test_failure_after_repair_and_lenient_raises_original_error():
    llm = FakeLLM(["", "still nothing"])
    with pytest.raises(PermanentEffectError) as ei:
        await structured_effect(
            await ctx_for(), llm, "r", MSGS, response_model=Out, lenient=lenient_json(Out)
        )
    assert ei.value.code == "structured_output_invalid" and len(llm.calls) == 2


async def test_non_structured_errors_are_not_retried():
    from gauntlet_core.llm.types import AuthError

    llm = FakeLLM([FakeReply(error=AuthError("no key"))])
    with pytest.raises(PermanentEffectError) as ei:
        await structured_effect(await ctx_for(), llm, "r", MSGS, response_model=Out)
    assert ei.value.code == "auth_error" and len(llm.calls) == 1


async def test_each_attempt_is_its_own_effect_and_replay_is_exact():
    store = MemoryJournalStore()
    ctx = await ctx_for(store)
    first = FakeLLM(["", '```json\n{"a": 9}\n```'])
    r1 = await structured_effect(
        ctx, first, "r", MSGS, response_model=Out, lenient=lenient_json(Out)
    )
    await ctx.flush()
    recorded = (await store.load("ep")).effects
    assert sorted(recorded) == ["llm:0", "llm:1"]
    assert all(rec.status == "failed" for rec in recorded.values())
    store.bump_epoch("ep")
    ctx2 = await ctx_for(store)
    second = FakeLLM([])  # replay: zero model calls
    r2 = await structured_effect(
        ctx2, second, "r", MSGS, response_model=Out, lenient=lenient_json(Out)
    )
    assert r2.parsed == r1.parsed == Out(a=9) and second.calls == []


async def test_structured_call_without_ctx():
    llm = FakeLLM(["bad", '{"a": 5}'])

    async def call(msgs):
        return await llm.complete("r", msgs, response_model=Out)

    assert (await structured_call(call, MSGS)).parsed == Out(a=5)


def test_extract_json_object_variants():
    assert extract_json_object('{"a": 1}') == {"a": 1}
    assert extract_json_object('text {"a": {"b": "}"}} tail') == {"a": {"b": "}"}}
    assert extract_json_object('```\n{"a": 1}\n```') == {"a": 1}
    assert extract_json_object('{"a": 1') is None
    assert extract_json_object("[1, 2]") is None


def test_repair_messages_shortens_the_error():
    msgs = repair_messages(MSGS, "x", "1 validation error for Out\n  Invalid JSON: EOF")
    assert "validation error for Out" not in msgs[-1]["content"] or True
    assert len(msgs[-1]["content"]) < 500
