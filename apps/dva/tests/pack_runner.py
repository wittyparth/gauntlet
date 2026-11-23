"""Run one pack scenario against the scripted DVA over the wired target. No model."""

from __future__ import annotations

import httpx
from gauntlet_core.checks import evaluate_final
from gauntlet_core.engine import EpisodeCtx, MemoryJournalStore, run_episode
from gauntlet_core.runner import make_finalizer
from gauntlet_core.schema import OpenAICompatTargetConfig, Scenario, WorldSpec
from gauntlet_core.sim import ScriptedUserSimulator
from gauntlet_core.targets import OpenAICompatTarget, UrlPolicy
from gauntlet_core.world import World, build_trajectory, build_world


def inline(scn: Scenario, world: WorldSpec) -> Scenario:
    return scn.model_copy(update={"world": world})


async def run_scenario_checks(world: WorldSpec, scn: Scenario, dva, facade) -> list[str]:
    """Ids of the forbidden checks that hold on the episode."""
    built = build_world(world, scn.world_overrides, 7)
    store = MemoryJournalStore()
    ctx = await EpisodeCtx.open(store, "ep_x", run_id="run_1", rng_seed=7)
    ctx.clock_start = world.clock_start
    World(built).bind(ctx)
    cfg = OpenAICompatTargetConfig(base_url=f"{dva}/v1", model="dva", wired=True)
    async with httpx.AsyncClient() as http:
        target = OpenAICompatTarget(
            cfg, secrets={}, client=http, safety=UrlPolicy(allow_private=True), facade=facade
        )
        await run_episode(
            ctx,
            scn,
            target,
            ScriptedUserSimulator([scn.opening_message or "hi"]),
            finalize=make_finalizer(scn, built, judge_enabled=False),
        )
    events = (await store.load("ep_x")).events
    traj = build_trajectory("ep_x", scn, events, built)
    return [n.id for n in scn.forbidden if evaluate_final(n.check, traj).holds]
