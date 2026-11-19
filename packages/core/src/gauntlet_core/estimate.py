"""Pre-run cost estimate (pure). Token counts are fixed planning assumptions, not measurements."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from gauntlet_core.llm import GatewayConfig
from gauntlet_core.llm.config import DEFAULT_MODEL
from gauntlet_core.schema import Scenario

__all__ = ["CostEstimate", "estimate_run_cost"]

SIM_TOKENS = (1500, 100)
AGENT_TOKENS = (2500, 200)
TOOL_ROUND_FACTOR = 1.5
JUDGE_SMALL_TOKENS = (3000, 300)
JUDGE_STRONG_TOKENS = (6000, 400)
ESCALATION_SHARE = 0.2


@dataclass(frozen=True)
class CostEstimate:
    low: int
    expected: int
    high: int
    warnings: tuple[str, ...] = field(default=())


def estimate_run_cost(
    scenarios: Sequence[Scenario],
    repetitions: int,
    gateway_config: GatewayConfig,
    *,
    rubric_count_by_scenario: Mapping[str, int] | None = None,
    agent_model: str | None = None,
) -> CostEstimate:
    llm = gateway_config.llm
    warnings: list[str] = []

    def price(model: str, tokens: tuple[int, int]) -> float:
        p = llm.pricing.get(model)
        if p is None:
            msg = f"no price for model {model}; counted as 0"
            if msg not in warnings:
                warnings.append(msg)
            return 0.0
        return (tokens[0] * p.input_per_mtok + tokens[1] * p.output_per_mtok) / 1_000_000

    def role_model(role: str) -> str:
        return llm.roles[role].model if role in llm.roles else DEFAULT_MODEL

    sim_m, small_m, strong_m = (role_model(r) for r in ("simulator", "judge_small", "judge_strong"))
    agent_m = agent_model or DEFAULT_MODEL
    total = 0.0
    for s in scenarios:
        turns = min(s.max_turns, 8)
        n_rub = (
            rubric_count_by_scenario.get(s.id, len(s.rubrics))
            if rubric_count_by_scenario is not None
            else len(s.rubrics)
        )
        total += turns * price(sim_m, SIM_TOKENS)
        total += turns * TOOL_ROUND_FACTOR * price(agent_m, AGENT_TOKENS)
        total += n_rub * (
            price(small_m, JUDGE_SMALL_TOKENS)
            + ESCALATION_SHARE * price(strong_m, JUDGE_STRONG_TOKENS)
        )
    expected = round(total * repetitions)
    return CostEstimate(
        low=round(0.6 * expected),
        expected=expected,
        high=round(1.8 * expected),
        warnings=tuple(warnings),
    )
