import json

import pytest
from gauntlet_core.engine import EpisodeCtx, MemoryBudgetLedger, MemoryJournalStore
from gauntlet_core.llm import FakeLLM
from gauntlet_core.schema import Cost
from gauntlet_core.security import (
    AttemptResult,
    PlacementError,
    UnsafeObjective,
    load_taxonomy,
    run_attacker,
)
from sec_helpers import attack


def proposal(payload, reasoning="r"):
    return json.dumps({"reasoning": reasoning, "payload": payload})


class MagicOracle:
    """Succeeds when the payload contains `magic`."""

    def __init__(self):
        self.calls: list[tuple[str, object]] = []

    async def __call__(self, atk, attempt_id, *, doc_body=None):
        self.calls.append((attempt_id, atk.payload))
        text = str(atk.payload)
        return AttemptResult(
            attempt_id, "magic" in text, reply_summary=f"reply to {text[:10]}", tools_called=("a",)
        )


async def open_ctx(store, run_id="atk_loop"):
    return await EpisodeCtx.open(store, "loop_1", run_id=run_id, rng_seed=5)


def script():
    return FakeLLM(
        by_role={
            "attacker": [proposal("first try"), proposal("second try"), proposal("magic words")],
            "judge_small": [json.dumps({"score": 2}), json.dumps({"score": 6})],
        }
    )


async def test_reaches_objective_on_round_three_with_progress_fed_back():
    store, llm, oracle = MemoryJournalStore(), script(), MagicOracle()
    ctx = await open_ctx(store)
    out = await run_attacker(ctx, llm, attack(), oracle, loop_id="L", profile_summary="support bot")
    assert out.success and out.stopped == "success" and len(out.rounds) == 3
    assert [r.progress for r in out.rounds] == [2, 6, None]
    assert out.winning_attack is not None and out.winning_attack.payload == "magic words"
    assert out.winning_attack.objective == attack().objective  # the model never edits the objective
    assert [c[0] for c in oracle.calls] == ["L:r1", "L:r2", "L:r3"]
    llm.assert_consumed()
    third_prompt = llm.calls[4].messages[1]["content"]  # attacker call of round 3
    assert "progress 0-10: 6" in third_prompt and "first try" in third_prompt
    assert "support bot" in third_prompt


async def test_replay_makes_no_model_calls_and_same_outcome():
    store = MemoryJournalStore()
    first = await run_attacker(
        await open_ctx(store), script(), attack(), MagicOracle(), loop_id="L", profile_summary="p"
    )
    empty = FakeLLM()  # any call would raise: the script is exhausted
    again = await run_attacker(
        await open_ctx(store), empty, attack(), MagicOracle(), loop_id="L", profile_summary="p"
    )
    assert empty.calls == []
    assert [r.payload for r in again.rounds] == [r.payload for r in first.rounds]
    assert again.success


async def test_stop_rule_attempts_exhausted_and_continue_after_success():
    llm = FakeLLM(
        by_role={
            "attacker": [proposal("a"), proposal("b")],
            "judge_small": [json.dumps({"score": 0}), json.dumps({"score": 1})],
        }
    )
    ctx = await open_ctx(MemoryJournalStore())
    out = await run_attacker(
        ctx, llm, attack(), MagicOracle(), loop_id="L", profile_summary="p", max_attempts=2
    )
    assert not out.success and out.stopped == "attempts" and len(out.rounds) == 2

    llm2 = FakeLLM(
        by_role={"attacker": [proposal("magic 1"), proposal("magic 2")], "judge_small": []}
    )
    out2 = await run_attacker(
        await open_ctx(MemoryJournalStore()), llm2, attack(), MagicOracle(), loop_id="L",
        profile_summary="p", max_attempts=2, stop_on_success=False,
    )  # fmt: skip
    assert len(out2.rounds) == 2 and out2.success


async def test_invalid_proposals_cost_a_round_but_do_not_run_an_episode():
    llm = FakeLLM(
        by_role={
            "attacker": [proposal("use {{evil}}"), proposal(""), proposal("magic")],
            "judge_small": [],
        }
    )
    oracle = MagicOracle()
    out = await run_attacker(
        await open_ctx(MemoryJournalStore()),
        llm,
        attack(),
        oracle,
        loop_id="L",
        profile_summary="p",
    )
    assert [r.error is not None for r in out.rounds] == [True, True, False]
    assert len(oracle.calls) == 1 and out.success


async def test_placement_error_is_a_failed_round():
    async def bad(atk, attempt_id, *, doc_body=None):
        raise PlacementError("no such record")

    llm = FakeLLM(by_role={"attacker": [proposal("x")], "judge_small": []})
    out = await run_attacker(
        await open_ctx(MemoryJournalStore()), llm, attack(), bad, loop_id="L",
        profile_summary="p", max_attempts=1,
    )  # fmt: skip
    assert out.rounds[0].error and "cannot place" in out.rounds[0].error


async def test_unsafe_objectives_are_refused_before_any_call():
    tax = load_taxonomy()
    llm = FakeLLM()
    ctx = await open_ctx(MemoryJournalStore())
    with pytest.raises(UnsafeObjective, match="harmful_content"):
        await run_attacker(
            ctx, llm, attack(category="harmful_content"), MagicOracle(), loop_id="L",
            profile_summary="p", taxonomy=tax,
        )  # fmt: skip
    with pytest.raises(UnsafeObjective, match="non-deterministic"):
        await run_attacker(
            ctx, llm, attack(objective={"type": "judge", "rubric": "r"}), MagicOracle(),
            loop_id="L", profile_summary="p", taxonomy=tax,
        )  # fmt: skip
    assert llm.calls == []


async def test_budget_exhaustion_stops_the_loop_cleanly():
    llm = FakeLLM(
        by_role={
            "attacker": [proposal("a"), proposal("b")],
            "judge_small": [json.dumps({"score": 1})],
        },
        default_cost=Cost(usd_micros=10),
    )
    ctx = await EpisodeCtx.open(
        MemoryJournalStore(), "loop_1", run_id="r", rng_seed=1, budget=MemoryBudgetLedger(25)
    )
    out = await run_attacker(ctx, llm, attack(), MagicOracle(), loop_id="L", profile_summary="p")
    assert out.stopped == "budget" and not out.success
