import json
import sys
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).parent))

from compile_helpers import TOOLS, batch, machine, model, rule, tool
from gauntlet_core.llm import FakeLLM, FakeReply
from gauntlet_core.policy import validate_policy
from gauntlet_core.policy.compile import compile_policy, default_action, default_severity
from gauntlet_core.schema import Policy, PolicyRule

SIX = """\
1. Refunds over 10000 cents require escalation to a human.
2. Only one coupon per order. Never stack codes.
3. Never reveal other customers' data.
4. Address changes should only happen while the order is processing.
5. After reading untrusted content, never send email.
6. Keep the conversation friendly.
"""


def six_batch():
    return batch(
        machine(
            "c01",
            rule(
                "refund-cap",
                tool("issue_refund", args={"amount_cents": {"gt": 10000}}),
                action="block",
                severity="low",
            ),
        ),
        machine("c02", rule("one-coupon", tool("apply_coupon", count={"min": 2}), action="log")),
        model("c03"),
        machine(
            "c04",
            rule(
                "addr",
                tool("update_address"),
                action="log",
                severity="critical",
            ),
            confidence=0.4,
        ),
        machine("c05", rule("taint", {"type": "tainted_call", "tool": "send_email"})),
        {"clause_id": "c06", "klass": "human", "confidence": 0.3, "rationale": "needs a person"},
    )


async def test_six_clauses_classes_rules_and_defaults():
    llm = FakeLLM(by_role={"generator": [FakeReply(parsed=six_batch())]})
    out = await compile_policy(SIX, tools=TOOLS, gateway=llm, policy_id="pol_x", seed=3)
    by = {p.clause_id: p for p in out.proposals}
    rules = {k: cast(PolicyRule, v.rule) for k, v in by.items()}
    assert [p.klass for p in out.proposals] == ["machine"] * 2 + ["model"] + ["machine"] * 2 + [
        "human"
    ]
    # keyword defaults override the model's severity and action
    assert (rules["c01"].action, rules["c01"].severity) == ("require_approval", "medium")
    assert (rules["c02"].action, rules["c02"].severity) == ("block", "high")
    assert (rules["c04"].action, rules["c04"].severity) == ("log", "medium")
    assert by["c03"].rubric is not None and by["c03"].rubric.id == "pol_x-c03"
    assert by["c04"].low_confidence and not by["c01"].low_confidence
    assert rules["c05"].message  # an agent-facing message is always present
    assert all(p.status == "proposed" for p in out.proposals)
    # every surviving rule is a loadable policy
    rules = [p.rule for p in out.proposals if p.rule]
    assert not validate_policy(Policy(id="pol_x", rules=rules))
    assert llm.calls[0].role == "generator"


async def test_prompt_has_schema_inventory_vocabulary_and_examples():
    llm = FakeLLM(by_role={"generator": [FakeReply(parsed=six_batch())]})
    await compile_policy(SIX, tools=TOOLS, gateway=llm, policy_id="p")
    system = llm.calls[0].messages[0]["content"]
    assert '"require_approval"' in system and "PolicyRule JSON Schema" in system
    assert "issue_refund" in system and "amount_cents" in system and "financial" in system
    assert "not allowed in rules" in system and "state_diff" in system
    assert system.count("clause: ") >= 6
    user = llm.calls[0].messages[1]["content"]
    assert json.loads(user.split("Clauses:\n")[1])[0]["clause_id"] == "c01"
    assert llm.calls[0].response_model is not None


async def test_batches_of_eight():
    text = "".join(f"{i}. Rule number {i}.\n" for i in range(1, 11))
    llm = FakeLLM(
        by_role={
            "generator": [
                FakeReply(parsed=batch(*[model(f"c{i:02d}") for i in range(1, 9)])),
                FakeReply(parsed=batch(model("c09"), model("c10"))),
            ]
        }
    )
    out = await compile_policy(text, tools=TOOLS, gateway=llm, policy_id="p")
    assert len(llm.calls) == 2 and len(out.proposals) == 10
    sent = json.loads(llm.calls[0].messages[1]["content"].split("Clauses:\n")[1])
    assert len(sent) == 8
    llm.assert_consumed()


async def test_invalid_batch_reply_is_repaired_once_then_human():
    llm = FakeLLM(by_role={"generator": ["not json", "still not json"]})
    out = await compile_policy("1. A.\n", tools=TOOLS, gateway=llm, policy_id="p")
    assert out.proposals[0].klass == "human" and len(llm.calls) == 2


def test_keyword_defaults():
    assert default_severity("You must not do X") == "high"
    assert default_severity("Prefer Y") == "medium"
    assert default_action("Needs approval") == "require_approval"
    assert default_action("Never do X") == "block"
    assert default_action("You should do X") == "log"
    assert default_action("Plain text") is None
