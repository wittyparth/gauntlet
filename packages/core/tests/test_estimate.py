from gauntlet_core.estimate import estimate_run_cost
from gauntlet_core.llm import GatewayConfig, LlmSection, PricingConfig, RoleConfig
from gauntlet_core.schema import Scenario


def scn(max_turns: int, rubrics: list[str]) -> Scenario:
    return Scenario.model_validate(
        {
            "id": f"s{max_turns}",
            "title": "t",
            "goal": "g",
            "persona": "p",
            "world": "w",
            "max_turns": max_turns,
            "rubrics": rubrics,
            "success": {"type": "output", "matcher": {"contains": "x"}},
        }
    )


def cfg(prices: dict[str, tuple[int, int]]) -> GatewayConfig:
    roles = {
        "simulator": RoleConfig(model="sim"),
        "judge_small": RoleConfig(model="small"),
        "judge_strong": RoleConfig(model="strong"),
    }
    return GatewayConfig(
        llm=LlmSection(
            roles=roles,
            pricing={
                m: PricingConfig(input_per_mtok=i, output_per_mtok=o)
                for m, (i, o) in prices.items()
            },
        )
    )


PRICES = {
    "sim": (1_000_000, 1_000_000),  # 1 usd micro per token
    "small": (1_000_000, 1_000_000),
    "strong": (1_000_000, 1_000_000),
    "agent": (1_000_000, 1_000_000),
}


def test_known_value():
    # turns=3: sim 3*(1500+100)=4800; agent 3*1.5*(2500+200)=12150;
    # judges 2 rubrics: 2*((3000+300) + 0.2*(6000+400)) = 2*(3300+1280)=9160
    est = estimate_run_cost([scn(3, ["a", "b"])], 2, cfg(PRICES), agent_model="agent")
    assert est.expected == (4800 + 12150 + 9160) * 2
    assert est.low == round(0.6 * est.expected) and est.high == round(1.8 * est.expected)
    assert est.warnings == ()


def test_turns_capped_at_eight_and_rubric_override():
    a = estimate_run_cost([scn(50, [])], 1, cfg(PRICES), agent_model="agent")
    b = estimate_run_cost([scn(8, [])], 1, cfg(PRICES), agent_model="agent")
    assert a.expected == b.expected
    c = estimate_run_cost(
        [scn(8, [])], 1, cfg(PRICES), agent_model="agent", rubric_count_by_scenario={"s8": 1}
    )
    assert c.expected == b.expected + 3300 + 1280


def test_unpriced_model_counts_zero_and_warns():
    prices = {k: v for k, v in PRICES.items() if k != "agent"}
    est = estimate_run_cost([scn(1, [])], 1, cfg(prices), agent_model="agent")
    assert est.expected == 1600
    assert any("agent" in w for w in est.warnings)
