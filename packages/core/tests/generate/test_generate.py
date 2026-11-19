from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from gauntlet_core.eval.rubrics import load_rubrics
from gauntlet_core.generate import generate_scenarios
from gauntlet_core.generate.dedupe import jaccard
from gauntlet_core.generate.outline import batch_plan, mix_counts
from gauntlet_core.llm import FakeLLM, FakeReply
from gauntlet_core.packs import load_pack
from gauntlet_core.schema import AgentProfile, Cost
from gauntlet_core.validate import validate_scenario
from gauntlet_core.world.openapi import import_openapi

REPO = Path(__file__).parents[4]
FIX = Path(__file__).parents[1] / "fixtures" / "openapi"
RUBRICS = sorted(load_rubrics())


@pytest.fixture(scope="module")
def pack():
    return load_pack(REPO / "packs" / "ecommerce")


@pytest.fixture
def profile(pack):
    return AgentProfile(
        purpose="Customer support for an outdoor gear store",
        audience="shoppers",
        policies_text=pack.policy_text,
        forbidden_behaviors=["promise refunds outside policy"],
    )


def outline(n: int = 1, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "title": f"Refund request {n}",
        "goal": f"unique goal number {n} about topic{n} words{n} alpha{n} beta{n}",
        "persona_id": "per_cooperative",
        "hidden_facts": ["Order is ord_1001"],
        "trap": None,
        "category": "happy",
        "expected_calls": [{"tool": "lookup_order", "args": {"order_id": "ord_1001"}}],
        "forbidden_calls": [{"tool": "apply_coupon", "args": {}}],
        "expected_output_contains": ["shipped"],
        "expected_state": [],
    }
    return {**base, **kw}


def batch(*outlines: dict[str, Any]) -> FakeReply:
    return FakeReply(parsed={"outlines": list(outlines)})


def single(**kw: Any) -> FakeReply:
    return FakeReply(parsed=outline(**kw))


async def run(pack, profile, llm: FakeLLM, **kw: Any):
    return await generate_scenarios(
        profile,
        pack.world,
        list(pack.personas.values()),
        llm,
        rubric_ids=RUBRICS,
        **kw,
    )


async def test_valid_outlines_compile_to_scenarios_that_validate(pack, profile):
    llm = FakeLLM(
        by_role={
            "generator": [
                batch(
                    outline(1),
                    outline(
                        2,
                        category="policy_edge",
                        expected_state=[
                            {
                                "collection": "orders",
                                "id": "ord_1002",
                                "path": "status",
                                "equals": "x",
                            }
                        ],
                    ),
                    outline(
                        3,
                        category="adversarial",
                        persona_id="per_social_engineer",
                        forbidden_calls=[
                            {"tool": "issue_refund", "args": {"order_id": "ord_1002"}}
                        ],
                    ),
                )
            ]
        }
    )
    res = await run(pack, profile, llm, count=3)
    assert len(res.scenarios) == 3 and res.dropped == []
    for scn in res.scenarios:
        issues = validate_scenario(
            scn, pack.world, persona_ids=set(pack.personas), rubric_ids=set(RUBRICS), strict=True
        )
        assert issues == []
        assert scn.tags["source"] == "generated" and scn.max_turns == 10
        assert scn.world == "ecommerce"
    first = res.scenarios[0]
    assert first.success.type == "all" and len(first.success.of) == 2
    assert first.rubrics == ["task_completion", "policy_adherence"]
    assert first.forbidden[0].id == "forbidden_0" and first.forbidden[0].severity == "high"
    assert res.scenarios[1].rubrics[-1] == "hallucinated_policy"
    assert res.scenarios[0].id != res.scenarios[1].id


async def test_unknown_tool_is_repaired_once(pack, profile):
    bad = outline(
        1, expected_calls=[{"tool": "refund_everything", "args": {}}], expected_output_contains=[]
    )
    llm = FakeLLM(by_role={"generator": [batch(bad), single(title="Fixed", goal="fixed goal x")]})
    res = await run(pack, profile, llm, count=1)
    assert [s.title for s in res.scenarios] == ["Fixed"] and res.dropped == []
    assert len(llm.calls) == 2
    repair_prompt = llm.calls[1].messages[-1]["content"]
    assert "unknown_tool" in repair_prompt and "refund_everything" in repair_prompt


async def test_unknown_tool_not_fixed_is_dropped_after_one_repair(pack, profile):
    bad = outline(1, expected_calls=[{"tool": "refund_everything", "args": {}}])
    llm = FakeLLM(by_role={"generator": [batch(bad), single(**bad)]})
    res = await run(pack, profile, llm, count=1)
    assert res.scenarios == []
    assert len(llm.calls) == 2
    assert res.dropped[0].title == "Refund request 1" and "unknown_tool" in res.dropped[0].reason


async def test_unknown_persona_record_and_empty_success_are_validated(pack, profile):
    outlines = [
        outline(1, persona_id="per_ghost"),
        outline(
            2,
            expected_state=[
                {"collection": "orders", "id": "ord_9999", "path": "status", "equals": 1}
            ],
        ),
        outline(3, expected_calls=[], expected_output_contains=[]),
        outline(4, hidden_facts=[]),
    ]
    llm = FakeLLM(by_role={"generator": [batch(*outlines), *[single(**o) for o in outlines]]})
    res = await run(pack, profile, llm, count=4)
    reasons = {d.title: d.reason for d in res.dropped}
    assert "unknown_persona" in reasons["Refund request 1"]
    assert "unknown_record" in reasons["Refund request 2"]
    assert "no_success_criteria" in reasons["Refund request 3"]
    assert "empty_hidden_facts" in reasons["Refund request 4"]


async def test_duplicates_dropped_within_batch_and_against_existing_titles(pack, profile):
    same_goal = "refund the delivered shoes from order ord_1001 because they are scratched"
    llm = FakeLLM(
        by_role={
            "generator": [
                batch(
                    outline(1, goal=same_goal),
                    outline(2, goal=same_goal + " today"),
                    outline(3, title="Already there"),
                )
            ]
        }
    )
    res = await run(pack, profile, llm, count=3, existing_titles=["Already there"])
    assert [s.title for s in res.scenarios] == ["Refund request 1"]
    assert {(d.title, d.reason) for d in res.dropped} == {
        ("Refund request 2", "duplicate"),
        ("Already there", "duplicate"),
    }
    assert jaccard("a b c", "a b c") == 1.0 and jaccard("", "x") == 0.0


async def test_category_mix_is_in_the_recorded_prompts(pack, profile):
    assert mix_counts(20, True) == {"happy": 8, "policy_edge": 5, "adversarial": 4, "error": 3}
    assert mix_counts(7, False)["adversarial"] == 0
    llm = FakeLLM(by_role={"generator": [batch(), batch()]})
    await run(pack, profile, llm, count=20, seed=5)
    assert len(llm.calls) == 2
    totals = {"happy": 0, "policy_edge": 0, "adversarial": 0, "error": 0}
    for call in llm.calls:
        prompt = call.messages[-1]["content"]
        line = re.search(r"Target mix: (.*)\.", prompt)
        assert line
        for cat, n in re.findall(r"(\w+)=(\d+)", line.group(1)):
            totals[cat] += int(n)
        assert "lookup_order [read]" in prompt and "orders: ord_1001, ord_1002" in prompt
        assert "per_social_engineer (adversarial)" in prompt
        assert "R3" in prompt  # policy text
    assert totals == {"happy": 8, "policy_edge": 5, "adversarial": 4, "error": 3}


async def test_adversarial_outlines_only_use_adversarial_personas(pack, profile):
    ok = outline(1, category="adversarial", persona_id="per_refund_abuser")
    bad = outline(2, category="adversarial", persona_id="per_cooperative")
    llm = FakeLLM(by_role={"generator": [batch(ok, bad), single(**bad)]})
    res = await run(pack, profile, llm, count=2)
    assert [s.persona for s in res.scenarios] == ["per_refund_abuser"]
    assert "persona_mismatch" in res.dropped[0].reason


async def test_cost_is_summed_over_batches_and_repairs(pack, profile):
    bad = outline(1, persona_id="per_ghost")
    llm = FakeLLM(
        by_role={"generator": [batch(bad), single(persona_id="per_cooperative")]},
        default_cost=Cost(usd_micros=250, input_tokens=10, output_tokens=5),
    )
    res = await run(pack, profile, llm, count=1)
    assert len(res.scenarios) == 1
    assert (res.cost.usd_micros, res.cost.input_tokens, res.cost.output_tokens) == (500, 20, 10)


async def test_deterministic_for_a_script_and_seed(pack, profile):
    def script():
        return FakeLLM(by_role={"generator": [batch(outline(1), outline(2)), batch(outline(3))]})

    a = await run(pack, profile, script(), count=12, seed=2)
    b = await run(pack, profile, script(), count=12, seed=2)
    assert [s.model_dump() for s in a.scenarios] == [s.model_dump() for s in b.scenarios]
    assert batch_plan(12, 2, True) == batch_plan(12, 2, True)
    assert any(batch_plan(12, s, True) != batch_plan(12, 2, True) for s in range(3, 10))


async def test_generated_scenario_for_an_imported_openapi_world_validates():
    imp = import_openapi(FIX / "shop.yaml", seed_per_collection=3)
    world = imp.to_world("shop", datetime(2026, 3, 15, tzinfo=UTC))
    pack = load_pack(REPO / "packs" / "ecommerce")
    o = outline(
        1,
        expected_calls=[{"tool": "get_order", "args": {"orderId": "order_1"}}],
        forbidden_calls=[{"tool": "delete_order", "args": {}}],
        expected_output_contains=[],
        expected_state=[
            {"collection": "orders", "id": "order_1", "path": "id", "equals": "order_1"}
        ],
    )
    llm = FakeLLM(by_role={"generator": [batch(o)]})
    res = await generate_scenarios(
        AgentProfile(purpose="Shop assistant"),
        world,
        list(pack.personas.values()),
        llm,
        count=1,
        rubric_ids=RUBRICS,
    )
    assert len(res.scenarios) == 1 and res.dropped == []
    scn = res.scenarios[0]
    assert validate_scenario(scn, world, persona_ids=set(pack.personas), strict=True) == []
    assert "get_order [read]" in llm.calls[0].messages[-1]["content"]
