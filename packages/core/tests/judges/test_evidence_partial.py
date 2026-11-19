"""Per-item evidence validation: drop bad items, re-anchor near misses (lead ruling)."""

import json
from pathlib import Path

import pytest
from gauntlet_core.engine import EpisodeCtx, MemoryJournalStore
from gauntlet_core.judges import JudgeOutput, normalize_text, run_stage, validate_evidence
from gauntlet_core.judges.evidence import check_evidence, sanitize
from gauntlet_core.judges.render import event_text
from gauntlet_core.llm import FakeLLM
from gauntlet_core.schema import Event
from judge_helpers import QUOTE, reply, rubric, traj

REAL = json.loads((Path(__file__).parent / "real_judge_outputs.json").read_text())


def out(result, evidence=(), conf=0.9):
    return JudgeOutput.model_validate(
        {
            "reasoning": "r",
            "evidence": [{"seq": s, "quote": q} for s, q in evidence],
            "result": result,
            "confidence": conf,
        }
    )


def real_case(case):
    evs = [Event.model_construct(**e) for e in case["events"]]
    texts = {e.seq: event_text(e) or "" for e in evs}
    actors = {e.seq: e.actor for e in evs}
    return texts, actors, JudgeOutput.model_validate(case["judge_output"])


@pytest.mark.parametrize("case", REAL, ids=lambda c: c["source"][-22:-16])
def test_real_cassette_outputs_now_validate(case):
    texts, actors, o = real_case(case)
    assert validate_evidence(o, texts, actors) == []
    check = check_evidence(o, texts, actors)
    assert check.dropped  # these outputs did carry bad items
    cleaned = sanitize(o, check)
    assert "evidence quote" in cleaned.reasoning and "dropped" in cleaned.reasoning
    for item in cleaned.evidence:
        assert normalize_text(item.quote).strip("\"'. ") in normalize_text(texts[item.seq])


def test_bad_items_dropped_good_kept_for_fail():
    texts = {1: "hello", 2: "Sure, I have refunded order 42 in full right now."}
    o = out("fail", [(2, QUOTE), (2, "xyz"), (2, "never said this at all")])
    check = check_evidence(o, texts)
    assert check.errors == [] and len(check.kept) == 1 and len(check.dropped) == 2
    assert "[2 evidence quotes dropped" in sanitize(o, check).reasoning


def test_fail_with_no_surviving_item_is_invalid():
    texts = {2: "Sure, I have refunded order 42 in full right now."}
    errs = validate_evidence(out("fail", [(2, "xyz"), (9, QUOTE)]), texts)
    assert any("shorter than 4" in e for e in errs) and any(
        "no event with seq 9" in e for e in errs
    )


def test_pass_and_na_valid_with_zero_surviving():
    texts = {2: "Sure, I have refunded order 42 in full right now."}
    assert validate_evidence(out("pass", [(2, "nonsense quote here")]), texts) == []
    assert validate_evidence(out("na", [(2, "nonsense quote here")]), texts) == []


def test_normalisation_dashes_curly_quotes_ellipses():
    texts = {2: "I'm sorry \u2014 that's not the quality we expect"}
    for q in (
        "I\u2019m sorry - that\u2019s not",
        '"that\'s not the quality..."',
        "\u2026that\u2019s not the quality\u2026",
        "I'M SORRY  \u2013  THAT'S",
    ):
        assert validate_evidence(out("fail", [(2, q)]), texts) == [], q


def test_min_length_is_four():
    texts = {2: "order ord_1004 shipped"}
    assert validate_evidence(out("fail", [(2, "ship")]), texts) == []
    assert validate_evidence(out("fail", [(2, "shi")]), texts) != []


def test_reanchor_same_actor_within_two_seq():
    texts = {
        3: "agent one",
        4: "tool says shipped",
        5: "I issued the refund now",
        9: "I issued the refund",
        12: "zz",
    }
    actors = {3: "agent", 4: "tool", 5: "agent", 9: "agent", 12: "agent"}
    q = "issued the refund"
    check = check_evidence(out("fail", [(3, q)]), texts, actors)
    assert check.errors == [] and [i.seq for i in check.kept] == [5]
    assert check_evidence(out("fail", [(4, q)]), texts, actors).errors  # other actor
    assert check_evidence(out("fail", [(12, q)]), texts, actors).errors  # 9 is 3 away
    assert check_evidence(out("fail", [(3, q)]), texts).errors  # no actors, no re-anchor


async def test_fail_without_valid_evidence_repairs_with_per_item_errors():
    f = FakeLLM(
        by_role={
            "judge_small": [reply("fail", 0.9, [(2, "xyz")]), reply("fail", 0.9, [(2, QUOTE)])]
        }
    )
    res = await run_stage(f, "judge_small", rubric(), traj())
    assert res.valid and len(f.calls) == 2
    assert "shorter than 4" in f.calls[1].messages[-1]["content"]


async def test_fail_with_one_good_item_needs_no_repair_and_notes_drops():
    f = FakeLLM(by_role={"judge_small": [reply("fail", 0.9, [(2, QUOTE), (2, "nope")])]})
    res = await run_stage(f, "judge_small", rubric(), traj())
    assert res.valid and len(f.calls) == 1
    assert res.output is not None and len(res.output.evidence) == 1
    assert "[1 evidence quote dropped" in res.output.reasoning


async def test_repair_is_its_own_journaled_llm_effect():
    store = MemoryJournalStore()
    ctx = await EpisodeCtx.open(store, "ep", run_id="r", rng_seed=1)
    replies: list = [reply("fail", 0.9, [(2, "xyz")]), reply("fail", 0.9, [(2, QUOTE)])]
    f = FakeLLM(by_role={"judge_small": replies})
    res = await run_stage(f, "judge_small", rubric(), traj(), ctx=ctx)
    assert res.valid and len(f.calls) == 2
    ctx2 = await EpisodeCtx.open(store, "ep", run_id="r", rng_seed=1)
    f2 = FakeLLM(by_role={"judge_small": []})
    res2 = await run_stage(f2, "judge_small", rubric(), traj(), ctx=ctx2)
    assert res2.valid and f2.calls == []  # both effects replayed from the journal
