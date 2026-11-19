from gauntlet_core.engine import EpisodeCtx, MemoryJournalStore, run_episode
from gauntlet_core.sim import ScriptedUserSimulator
from sim_helpers import EchoTarget, scenario


async def run(sim):
    store = MemoryJournalStore()
    ctx = await EpisodeCtx.open(store, "ep", run_id="r", rng_seed=1)
    res = await run_episode(ctx, scenario(max_turns=4), EchoTarget(), sim)
    return res, [e.payload["text"] for e in ctx.trajectory_so_far if e.kind == "user_message"]


async def test_turns_in_order_then_done():
    res, said = await run(ScriptedUserSimulator(["a", "b"]))
    assert said == ["a", "b"] and res.termination == "user_done"


async def test_repeat_last_runs_to_max_turns():
    res, said = await run(ScriptedUserSimulator(["a", "b"], then="repeat_last"))
    assert said == ["a", "b", "b", "b"] and res.termination == "max_turns"
