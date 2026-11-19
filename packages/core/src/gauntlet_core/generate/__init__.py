"""Scenario generation from an agent profile: outlines from a model, checks from code.

Generated scenarios carry no status; the server stores them as `draft` (P1-9)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from gauntlet_core.llm import Gateway, GatewayError
from gauntlet_core.schema import AgentProfile, Cost, Persona, Scenario, WorldSpec

from .compile import compile_outline, outline_issues
from .dedupe import is_duplicate
from .outline import (
    Outline,
    OutlineBatch,
    batch_plan,
    build_messages,
    build_repair_messages,
)

__all__ = [
    "Dropped",
    "GenerationResult",
    "compile_outline",
    "generate_scenarios",
]

ROLE = "generator"


@dataclass(frozen=True)
class Dropped:
    title: str
    reason: str


@dataclass
class GenerationResult:
    scenarios: list[Scenario] = field(default_factory=list)
    dropped: list[Dropped] = field(default_factory=list)
    cost: Cost = field(default_factory=Cost)


async def generate_scenarios(
    profile: AgentProfile,
    world: WorldSpec,
    personas: Sequence[Persona],
    gateway: Gateway,
    *,
    count: int = 20,
    seed: int = 0,
    existing_titles: Sequence[str] = (),
    rubric_ids: Sequence[str] = (),
) -> GenerationResult:
    pmap = {p.id: p for p in personas}
    result = GenerationResult()
    goals: list[str] = []
    plan = batch_plan(count, seed, any(p.adversarial_intent for p in personas))
    for i, mix in enumerate(plan):
        messages = build_messages(
            profile,
            world,
            personas,
            mix,
            batch_index=i,
            rotation=seed,
            existing_titles=[*existing_titles, *(s.title for s in result.scenarios)],
        )
        try:
            res = await gateway.complete(
                "generator", messages, response_model=OutlineBatch, seed=seed + i
            )
        except GatewayError as e:
            result.dropped.append(Dropped(f"batch {i + 1}", f"llm_error: {e}"))
            continue
        result.cost = result.cost + res.cost
        if not isinstance(res.parsed, OutlineBatch):
            result.dropped.append(Dropped(f"batch {i + 1}", "llm_error: no parsed outlines"))
            continue
        for outline in res.parsed.outlines[: sum(mix.values())]:
            if is_duplicate(outline.goal, goals) or is_duplicate(outline.title, existing_titles):
                result.dropped.append(Dropped(outline.title, "duplicate"))
                continue
            scn, issues = outline_issues(outline, world, pmap, rubric_ids=rubric_ids)
            if issues:
                fixed, issues, cost = await _repair(
                    gateway, messages, outline, issues, world, pmap, rubric_ids, seed + i
                )
                result.cost = result.cost + cost
                if issues or fixed is None:
                    result.dropped.append(Dropped(outline.title, "; ".join(issues)))
                    continue
                scn = fixed
            if scn is not None:
                goals.append(scn.goal)
                result.scenarios.append(scn)
    result.scenarios = result.scenarios[:count]
    return result


async def _repair(
    gateway: Gateway,
    base: list,
    outline: Outline,
    issues: list[str],
    world: WorldSpec,
    pmap: dict[str, Persona],
    rubric_ids: Sequence[str],
    seed: int,
) -> tuple[Scenario | None, list[str], Cost]:
    """One repair call listing the issues. Returns the scenario, remaining issues, cost."""
    try:
        res = await gateway.complete(
            ROLE,
            build_repair_messages(base, outline, issues),
            response_model=Outline,
            seed=seed,
        )
    except GatewayError as e:
        return None, [*issues, f"repair_failed: {e}"], Cost()
    if not isinstance(res.parsed, Outline):
        return None, [*issues, "repair_failed: no parsed outline"], res.cost
    scn, remaining = outline_issues(res.parsed, world, pmap, rubric_ids=rubric_ids)
    return scn, remaining, res.cost
