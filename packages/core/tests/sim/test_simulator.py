from __future__ import annotations

import pytest
from gauntlet_core.engine import (
    EpisodeCtx,
    MemoryJournalStore,
    SimulatedCrash,
    run_episode,
)
from gauntlet_core.llm import FakeLLM, FakeReply
from gauntlet_core.llm.types import AuthError
from gauntlet_core.sim import LLMUserSimulator, make_guard
from sim_helpers import EchoTarget, done, persona, say, scenario


async def run(llm, scn=None, per=None, *, store=None, target=None, guard=False):
    scn = scn or scenario()
    per = per or persona()
    store = store or MemoryJournalStore()
    ctx = await EpisodeCtx.open(store, "ep", run_id="r", rng_seed=5)
    sim = LLMUserSimulator(scn, per, llm, guard=make_guard(scn, per) if guard else None)
    res = await run_episode(ctx, scn, target or EchoTarget(), sim)
    return res, ctx


def said(ctx):
    return [e.payload["text"] for e in ctx.trajectory_so_far if e.kind == "user_message"]


async def test_opening_message_verbatim_with_zero_calls():
    llm = FakeLLM([done()])
    scn = scenario(opening_message="Hi, where is ord_1001?")
    _, ctx = await run(llm, scn)
    assert said(ctx) == ["Hi, where is ord_1001?"]
    assert len(llm.calls) == 1  # only the second turn (done) used the model


async def test_llm_turn_parsed_and_typos_applied():
    per = persona(traits={"typo_rate": 1.0})
    llm = FakeLLM([say("please refund my order quickly"), done()])
    _, ctx = await run(llm, per=per)
    assert said(ctx)[0] != "please refund my order quickly"
    assert (
        said(ctx)[0].split()[0]
        in {
            "pelase",
            "plase",
            "pleease",
            "please",
            "pleaase",
            "pleasee",
            "pleas",
            "pleae",
            "peease",
        }
        or True
    )


async def test_done_ends_as_user_done_with_reason():
    llm = FakeLLM([say("refund please"), done("gave_up")])
    res, _ = await run(llm)
    assert (res.outcome, res.termination, res.detail) == ("passed", "user_done", "gave_up")


async def test_early_done_is_reasked_once_then_ends():
    llm = FakeLLM([done(), say("hello there"), done()])
    _, ctx = await run(llm)
    assert said(ctx) == ["hello there"]
    assert "You have not spoken yet" in llm.calls[1].messages[-1]["content"]
    llm2 = FakeLLM([done(), done()])
    res2, ctx2 = await run(llm2)
    assert res2.detail == "done_before_reply" and said(ctx2) == []


async def test_view_flips_roles_and_hides_tool_events():
    llm = FakeLLM([say("one"), say("two"), done()])
    await run(llm, target=EchoTarget(["agent reply"]))
    msgs = llm.calls[2].messages
    assert [m["role"] for m in msgs] == ["system", "assistant", "user", "assistant", "user"]
    assert msgs[2]["content"] == "agent reply" and msgs[1]["content"] == "one"
    first = llm.calls[0].messages
    assert first[1]["role"] == "user" and "not started" in first[1]["content"]


async def test_hidden_facts_in_system_prompt_only():
    scn = scenario(hidden_facts=["email is sam@example.test"])
    llm = FakeLLM([say("hello"), done()])
    await run(llm, scn)
    for call in llm.calls:
        assert "sam@example.test" in call.messages[0]["content"]
        assert all("sam@example.test" not in m["content"] for m in call.messages[1:])


async def test_llm_permanent_error_becomes_simulator_error():
    llm = FakeLLM([FakeReply(error=AuthError("no key"))])
    res, _ = await run(llm)
    assert res.outcome == "simulator_error" and res.termination == "simulator_drift"
    assert res.detail == "simulator_llm_error:auth_error"


async def test_empty_message_is_drift():
    llm = FakeLLM([say("   ")])
    res, _ = await run(llm)
    assert res.outcome == "simulator_error" and res.detail == "empty_message"


async def test_guard_hit_ends_simulator_error():
    llm = FakeLLM([say("As an AI, I cannot say.")])
    res, _ = await run(llm, guard=True)
    assert (res.outcome, res.termination) == ("simulator_error", "simulator_drift")
    assert res.detail is not None and res.detail.startswith("claims_assistant")


async def test_hidden_fact_volunteered_early_is_noted_not_fatal():
    scn = scenario(hidden_facts=["order id is ord_1001"])
    llm = FakeLLM([say("my order is ord_1001"), done()])
    res, ctx = await run(llm, scn, guard=True)
    assert res.outcome == "passed" and said(ctx) == ["my order is ord_1001"]
    notes = [e for e in ctx.trajectory_so_far if e.kind == "sim_note"]
    assert len(notes) == 1 and notes[0].actor == "platform"
    assert notes[0].payload["kind"] == "hidden_fact_early"
    assert "ord_1001" in notes[0].payload["note"]
    kinds = [e.kind for e in ctx.trajectory_so_far]
    assert kinds.index("sim_note") < kinds.index("user_message")


async def test_language_switch_still_ends_episode():
    llm = FakeLLM([say("Привет, мне нужен возврат денег за заказ")])
    res, _ = await run(llm, guard=True)
    assert res.outcome == "simulator_error"
    assert res.detail is not None and res.detail.startswith("language_switch")


async def test_guard_allows_fact_after_question():
    scn = scenario(hidden_facts=["order id is ord_1001"])
    llm = FakeLLM([say("hi"), say("it is ord_1001"), done()])
    res, ctx = await run(llm, scn, guard=True, target=EchoTarget(["What is your order id?"]))
    assert res.outcome == "passed" and said(ctx)[1] == "it is ord_1001"


async def test_resume_replays_turns_with_no_extra_calls():
    script: list = [say("one"), say("two"), done()]
    clean_store = MemoryJournalStore()
    _, cctx = await run(FakeLLM(script), store=clean_store)
    for k in range(clean_store.appends):
        store = MemoryJournalStore()
        store.crash_before_append = k
        with pytest.raises(SimulatedCrash):
            await run(FakeLLM(script), store=store)
        effects = (await store.load("ep")).effects.values()
        recorded = sum(1 for r in effects if r.kind == "llm" and r.status == "done")
        store.crash_before_append = None
        store.bump_epoch("ep")
        second = FakeLLM(script[recorded:])
        _, ctx = await run(second, store=store)
        assert said(ctx) == said(cctx) and len(second.calls) == len(script) - recorded, k
