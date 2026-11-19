"""Running attack episodes: the bridge from the security core to the shared runner.

`EpisodeScenarioRunner` runs one *placed* scenario through `execute_with_attempts` (so crash
resume, replay and the abandon-attempt path are the engine's) and reads the objective result
back from the journal. `attack_oracle` adds placement in front of it. Episode ids are
`<namespace>:<attempt_id>`; callers derive attempt ids deterministically, so re-running a loop
after a crash maps every attempt onto the journal it already wrote and replays it for free."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Protocol

from gauntlet_core.engine import UserSimulator
from gauntlet_core.runner import EpisodeJob, RunnerDeps, derive_episode_seed, execute_with_attempts
from gauntlet_core.schema import AgentVersion, Attack, Persona, Rubric, Scenario, WorldSpec
from gauntlet_core.sim import ScriptedUserSimulator

from .objectives import AttemptResult, result_from_events
from .placement import TURNS_TAG, place

__all__ = ["AttackOracle", "EpisodeScenarioRunner", "ScenarioRunner", "attack_oracle"]


class ScenarioRunner(Protocol):
    async def __call__(
        self, scenario: Scenario, world: WorldSpec, attempt_id: str, /
    ) -> AttemptResult: ...


class AttackOracle(Protocol):
    """Place `attack` into the base world and run one fresh episode."""

    async def __call__(
        self, attack: Attack, attempt_id: str, /, *, doc_body: str | None = None
    ) -> AttemptResult: ...


class EpisodeScenarioRunner:
    def __init__(
        self,
        deps: RunnerDeps,
        agent_version: AgentVersion,
        persona: Persona,
        *,
        rubrics: dict[str, Rubric] | None = None,
        namespace: str = "atk",
        seed: int = 0,
        secrets: dict[str, str] | None = None,
        sim_factory: Callable[[Scenario], UserSimulator] | None = None,
    ) -> None:
        self.deps, self.agent_version, self.persona = deps, agent_version, persona
        self.rubrics, self.namespace, self.seed = rubrics or {}, namespace, seed
        self.secrets, self.sim_factory = secrets or {}, sim_factory

    @property
    def agent_version_id(self) -> str:
        return self.agent_version.id

    async def __call__(
        self, scenario: Scenario, world: WorldSpec, attempt_id: str
    ) -> AttemptResult:
        episode_id = f"{self.namespace}:{attempt_id}"
        job = EpisodeJob(
            episode_id=episode_id,
            run_id=self.namespace,
            scenario=scenario,
            world=world,
            agent_version=self.agent_version,
            persona=self.persona,
            rubrics=self.rubrics,
            rng_seed=derive_episode_seed(self.seed, attempt_id, 0),
            secrets=self.secrets,
        )
        sim: UserSimulator | None = None
        if TURNS_TAG in scenario.tags:
            sim = ScriptedUserSimulator(json.loads(scenario.tags[TURNS_TAG]))
        elif self.sim_factory is not None:
            sim = self.sim_factory(scenario)
        out = await execute_with_attempts(job, self.deps, sim=sim)
        events = (await self.deps.store.load(episode_id)).events
        risk = {t.name: t.risk for t in world.tools}
        return result_from_events(episode_id, events, risk, cost_usd_micros=out.cost.usd_micros)


def attack_oracle(
    runner: ScenarioRunner,
    world: WorldSpec,
    scenario: Scenario,
    *,
    seed: int = 0,
) -> AttackOracle:
    """`place` then run. `seed` fixes the taint marker, so every candidate derived from one
    attack id carries the same marker."""

    async def run(attack: Attack, attempt_id: str, *, doc_body: str | None = None) -> AttemptResult:
        placed = place(attack, world, scenario, seed=seed, doc_body=doc_body)
        return await runner(placed.scenario, placed.world, attempt_id)

    return run
