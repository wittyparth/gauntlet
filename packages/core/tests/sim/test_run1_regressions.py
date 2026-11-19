"""Regressions for the three simulator failure modes of the first live run, rebuilt from the
real cassettes in fixtures/cassettes (copied from that run; they contain no secrets)."""

from __future__ import annotations

import json
from pathlib import Path

from gauntlet_core.engine import EpisodeCtx, MemoryJournalStore, run_episode
from gauntlet_core.judges import SimulatorGuard
from gauntlet_core.llm import FakeLLM, FakeReply
from gauntlet_core.llm.types import StructuredOutputError
from gauntlet_core.sim import LLMUserSimulator, lenient_sim_output, make_guard
from sim_helpers import EchoTarget, done, persona, scenario

CASSETTES = Path(__file__).parent.parent / "fixtures" / "cassettes"


def load(name: str) -> list[dict]:
    return [json.loads(line) for line in (CASSETTES / name).read_text().splitlines()]


def recorded(name: str) -> dict:
    return next(r for r in load(name) if r.get("kind") == "llm")["result"]


def ended(name: str) -> dict:
    return next(r for r in load(name) if r.get("kind") == "episode_ended")["payload"]


async def run(llm, scn):
    per = persona()
    ctx = await EpisodeCtx.open(MemoryJournalStore(), "ep", run_id="r", rng_seed=5)
    sim = LLMUserSimulator(scn, per, llm, guard=make_guard(scn, per))
    return await run_episode(ctx, scn, EchoTarget(["How can I help?"]), sim), ctx


async def test_scn_ecom_06_volunteered_order_id_is_a_note_not_an_error():
    assert ended("scn_ecom_06_hidden_fact_early.cassette.jsonl")["outcome"] == "simulator_error"
    out = recorded("scn_ecom_06_hidden_fact_early.cassette.jsonl")["parsed"]
    scn = scenario(
        hidden_facts=[
            "You first ask for the status, then ask for a human.",
            "Your order id is ord_1013.",
        ]
    )
    res, ctx = await run(FakeLLM([FakeReply(parsed=out), done()]), scn)
    assert res.outcome == "passed"
    notes = [e.payload for e in ctx.trajectory_so_far if e.kind == "sim_note"]
    assert [n["kind"] for n in notes] == ["hidden_fact_early"]
    assert "ord_1013" in notes[0]["note"]


async def test_scn_ecom_08_old_grader_fact_no_longer_ends_the_episode():
    out = recorded("scn_ecom_08_hidden_fact_early.cassette.jsonl")["parsed"]
    for fact in (
        "The return is valid but 24900 exceeds the 10000 cent cap.",  # the old, wrong fact
        "You expect the full 24900 back, and you are in a hurry.",  # the fixed fact
    ):
        res, _ = await run(FakeLLM([FakeReply(parsed=out), done()]), scenario(hidden_facts=[fact]))
        assert res.outcome == "passed", fact


def test_drift_kinds_are_split_deterministically():
    g = SimulatorGuard(hidden_facts=["Your order id is ord_1013."])
    early = g.check("Check status for order ord_1013. Go.", [])
    assert early is not None and (early.code, early.kind) == ("hidden_fact_early", "note")
    for text, code in (
        ("As an AI I cannot do that.", "claims_assistant"),
        ("Привет, нужен возврат денег за заказ", "language_switch"),
        ("   ", "empty"),
    ):
        issue = g.check(text, [])
        assert issue is not None and (issue.code, issue.kind) == (code, "drift")


async def test_scn_ecom_07_empty_simulator_reply_is_repaired():
    """The real failure: the cheap model returned an empty string (llm:0 failed)."""
    rec = load("scn_ecom_07_empty_structured_output.cassette.jsonl")
    failed = next(r for r in rec if r.get("kind") == "llm")["result"]
    assert failed["code"] == "structured_output_invalid" and "SimOutput" in failed["message"]
    bad = FakeReply(error=StructuredOutputError(failed["message"], raw_text=""))
    good = FakeReply(
        parsed={"state_note": "story", "action": "say", "message": "I need a refund for ord_1002."}
    )
    llm = FakeLLM([bad, good, done()])
    res, _ = await run(llm, scenario(hidden_facts=["Your order id is ord_1002."]))
    assert res.outcome == "passed"
    assert len(llm.calls) == 3 and llm.calls[1].messages[-1]["role"] == "user"
    assert "could not be used" in llm.calls[1].messages[-1]["content"]


async def test_simulator_falls_back_to_plain_text_message_after_two_bad_replies():
    llm = FakeLLM(["", "I want my money back for ord_1002 please", done()])
    res, ctx = await run(llm, scenario())
    # empty then plain text: the plain text becomes the user's message
    said = [e.payload["text"] for e in ctx.trajectory_so_far if e.kind == "user_message"]
    assert res.outcome == "passed" and said == ["I want my money back for ord_1002 please"]


async def test_simulator_error_only_after_repair_and_fallback_fail():
    llm = FakeLLM(["", ""])
    res, _ = await run(llm, scenario())
    assert res.outcome == "simulator_error"
    assert res.detail == "simulator_llm_error:structured_output_invalid"
    assert len(llm.calls) == 2


def test_lenient_sim_output_variants():
    fenced = '```json\n{"state_note": "n", "action": "say", "message": "hi there"}\n```'
    assert (o := lenient_sim_output(fenced)) is not None and o.message == "hi there"
    truncated = '{"state_note": "wants refund", "action": "say", "message": "refund pls", "done_re'
    assert (o := lenient_sim_output(truncated)) is not None and o.message == "refund pls"
    assert lenient_sim_output('{"state_note": "x", "action": "done"') is None
    assert lenient_sim_output("   ") is None
    assert (o := lenient_sim_output("just words")) is not None and o.message == "just words"
