import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from compile_helpers import TOOLS, batch, machine, model, rubric, rule, tool
from gauntlet_core.llm import FakeLLM, FakeReply
from gauntlet_core.policy.compile import check_rule, compile_policy


def test_valid_rule_survives():
    res = check_rule(rule("r", tool("issue_refund", args={"amount_cents": {"gt": 5}})), TOOLS)
    assert res.ok


def test_judge_node_is_fatal():
    res = check_rule(rule("r", {"type": "judge", "rubric": "x"}), TOOLS)
    assert res.fatal and not res.ok and "judge" in res.fatal[0]


def test_unknown_tool_and_argument_are_repairable():
    assert check_rule(rule("r", tool("nope")), TOOLS).repairable
    res = check_rule(rule("r", tool("issue_refund", args={"bogus": {"eq": 1}})), TOOLS)
    assert res.repairable and not res.fatal


def test_schema_error_is_fatal():
    assert check_rule({"id": "r"}, TOOLS).fatal


async def test_judge_rule_is_downgraded_to_model_with_rubric():
    llm = FakeLLM(
        by_role={
            "generator": [
                FakeReply(
                    parsed=batch(machine("c01", rule("r", {"type": "judge", "rubric": "x"})))
                ),
                FakeReply(parsed=rubric("drafted")),  # the rubric call
            ]
        }
    )
    out = await compile_policy("1. Be polite.\n", tools=TOOLS, gateway=llm, policy_id="pol_1")
    p = out.proposals[0]
    assert p.klass == "model" and p.rule is None and p.rubric is not None
    assert "Downgraded" in p.rationale and "judge" in p.rationale
    llm.assert_consumed()


async def test_unknown_tool_repaired_once_then_downgraded():
    bad = machine("c01", rule("r", tool("nope")))
    repaired = {**machine("c01", rule("r", tool("issue_refund")))}
    llm = FakeLLM(by_role={"generator": [FakeReply(parsed=batch(bad)), FakeReply(parsed=repaired)]})
    out = await compile_policy("1. Never refund.\n", tools=TOOLS, gateway=llm, policy_id="pol_1")
    assert out.proposals[0].klass == "machine" and out.proposals[0].rule is not None
    assert len(llm.calls) == 2  # one batch call, one repair call

    still_bad = FakeLLM(
        by_role={
            "generator": [
                FakeReply(parsed=batch(bad)),
                FakeReply(parsed=bad),
                FakeReply(parsed=rubric("d")),
            ]
        }
    )
    out = await compile_policy("1. Never refund.\n", tools=TOOLS, gateway=still_bad, policy_id="p")
    assert out.proposals[0].klass == "model" and "nope" in out.proposals[0].rationale
    assert len(still_bad.calls) == 3


async def test_model_class_without_rubric_and_failed_draft_becomes_human():
    llm = FakeLLM(
        by_role={
            "generator": [
                FakeReply(parsed=batch({"clause_id": "c01", "klass": "model"})),
                FakeReply(parsed={"not": "a rubric"}),
            ]
        }
    )
    out = await compile_policy("1. Be nice.\n", tools=TOOLS, gateway=llm, policy_id="p")
    assert out.proposals[0].klass == "human"


async def test_missing_clause_in_reply_is_human_zero_confidence():
    llm = FakeLLM(by_role={"generator": [FakeReply(parsed=batch(model("c01")))]})
    out = await compile_policy("1. a\n2. b\n", tools=TOOLS, gateway=llm, policy_id="p")
    assert out.proposals[1].klass == "human" and out.proposals[1].confidence == 0.0
