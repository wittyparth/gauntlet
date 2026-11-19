"""Every scenario has a good and a bad scripted trajectory, run through a real World and the
deterministic checks (`evaluate_final`). No LLM."""

from __future__ import annotations

import pytest
from gauntlet_core.checks import evaluate_final
from gauntlet_core.engine import EpisodeCtx, MemoryJournalStore, run_episode
from gauntlet_core.sim import ScriptedUserSimulator
from gauntlet_core.world import World, build_trajectory, build_world
from oracles import ORACLES


class ScriptedAgent:
    stateful = False

    def __init__(self, world, calls, text):
        self.world, self.calls, self.text = world, calls, text

    async def open(self, ctx):
        pass

    async def close(self, ctx):
        pass

    async def send(self, ctx, user_text):
        for tool, args in self.calls:
            await self.world.call_tool(ctx, tool, args)
        return self.text


async def evaluate(pack, scn, run):
    calls, text = run
    built = build_world(pack.world, scn.world_overrides, 7)
    text = text.replace("{card}", built.canaries[0].value)
    store = MemoryJournalStore()
    ctx = await EpisodeCtx.open(store, "ep_1", run_id="run_1", rng_seed=7)
    world = World(built)
    await run_episode(ctx, scn, ScriptedAgent(world, calls, text), ScriptedUserSimulator(["hi"]))
    traj = build_trajectory("ep_1", scn, (await store.load("ep_1")).events, built)
    success = evaluate_final(scn.success, traj)
    forbidden = {n.id: evaluate_final(n.check, traj).holds for n in scn.forbidden}
    return success.holds, [k for k, v in forbidden.items() if v]


def test_every_scenario_has_an_oracle_pair(pack):
    assert sorted(ORACLES) == list(range(1, 31))
    assert len(pack.scenarios) == 30


@pytest.mark.parametrize("n", range(1, 31))
async def test_good_trajectory_passes(pack, n):
    scn = pack.scenarios[f"scn_ecom_{n:02d}"]
    success, sprung = await evaluate(pack, scn, ORACLES[n][0])
    assert success, "success check must hold on the good run"
    assert sprung == [], f"forbidden checks fired on the good run: {sprung}"


@pytest.mark.parametrize("n", range(1, 31))
async def test_bad_trajectory_fails(pack, n):
    scn = pack.scenarios[f"scn_ecom_{n:02d}"]
    success, sprung = await evaluate(pack, scn, ORACLES[n][1])
    assert (not success) or sprung, "the bad run must fail success or spring a forbidden check"


@pytest.mark.parametrize("n", [7, 8, 10, 11, 13, 14, 15, 17, 19, 22, 23, 24, 29])
async def test_trap_scenarios_spring_a_forbidden_check(pack, n):
    scn = pack.scenarios[f"scn_ecom_{n:02d}"]
    _, sprung = await evaluate(pack, scn, ORACLES[n][1])
    assert sprung, "the bad run of a trap scenario names a forbidden check"
