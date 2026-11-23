"""Run scripted tool calls through a pack's world and evaluate checks (no model)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gauntlet_core.checks import evaluate_final
from gauntlet_core.engine import EpisodeCtx, MemoryJournalStore, run_episode
from gauntlet_core.packs import Pack
from gauntlet_core.schema import Check, Scenario
from gauntlet_core.sim import ScriptedUserSimulator
from gauntlet_core.world import World, build_trajectory, build_world

FIXTURES = Path(__file__).parents[3] / "tests" / "fixtures" / "benchmarks"


async def run_calls(
    pack: Pack, scn: Scenario, calls: list[tuple[str, dict[str, Any]]], text: str = "done"
) -> Any:
    world = pack.worlds[str(scn.world)]
    built = build_world(world, scn.world_overrides, 7)
    store = MemoryJournalStore()
    ctx = await EpisodeCtx.open(store, "ep_1", run_id="run_1", rng_seed=7)
    ctx.clock_start = world.clock_start
    w = World(built)

    class Agent:
        stateful = False

        async def open(self, ctx):
            pass

        async def close(self, ctx):
            pass

        async def send(self, ctx, user_text):
            for tool, args in calls:
                await w.call_tool(ctx, tool, args)
            return text

    await run_episode(ctx, scn, Agent(), ScriptedUserSimulator(["hi"]))
    return build_trajectory("ep_1", scn, (await store.load("ep_1")).events, built)


def holds(check: Check, traj: Any) -> bool:
    return evaluate_final(check, traj).holds
