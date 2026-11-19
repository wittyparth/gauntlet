from collections import Counter

import pytest
from gauntlet_core.engine import (
    EpisodeCtx,
    IndeterminateEffect,
    MemoryBudgetLedger,
    MemoryJournalStore,
    NonDeterminism,
    SimTurn,
    SimulatedCrash,
    StaleLease,
    TargetError,
    dump_cassette,
    redact,
    run_episode,
    store_from_cassette,
)
from gauntlet_core.schema import Cost, Scenario
from hypothesis import given, settings
from hypothesis import strategies as st

EP = "ep_1"


def go(ctx, scn, sim, agent):
    return run_episode(ctx, scn, agent, sim)


def scenario(max_turns: int = 12) -> Scenario:
    return Scenario.model_validate(
        {
            "id": "scn",
            "title": "t",
            "goal": "g",
            "persona": "p",
            "world": "w",
            "max_turns": max_turns,
            "success": {"type": "output", "matcher": {"contains": "x"}},
        }
    )


class Sim:
    def __init__(self, turns: list[str], calls: Counter, cost: int = 0) -> None:
        self.turns, self.calls, self.cost = turns, calls, cost

    async def next_message(self, ctx: EpisodeCtx) -> SimTurn:
        n = sum(1 for e in ctx.trajectory_so_far if e.kind == "user_message")

        async def fn():
            self.calls[f"sim:{n}"] += 1
            text = self.turns[n] if n < len(self.turns) else None
            return {"text": text}, Cost(usd_micros=self.cost)

        res = await ctx.effect("llm", {"turn": n}, fn, retry_safe=True, est_usd_micros=self.cost)
        return SimTurn("message", res["text"]) if res["text"] is not None else SimTurn("done")


class Agent:
    def __init__(self, calls: Counter, stateful: bool = False, reply=None, die_on=None) -> None:
        self.calls, self.stateful, self.die_on = calls, stateful, die_on
        self.reply = reply or (lambda text: f"re: {text}")

    async def open(self, ctx):
        pass

    async def close(self, ctx):
        pass

    async def send(self, ctx: EpisodeCtx, user_text: str) -> str:
        async def fn():
            self.calls[f"agent:{user_text}"] += 1
            if self.die_on == user_text and self.calls[f"agent:{user_text}"] == 1:
                raise SimulatedCrash
            out = self.reply(user_text)
            if isinstance(out, Exception):
                raise out
            return {"reply": out}, None

        res = await ctx.effect("target", {"text": user_text}, fn, retry_safe=not self.stateful)
        return res["reply"]


async def run(store, turns, calls=None, **agent_kw):
    calls = calls if calls is not None else Counter()
    ctx = await EpisodeCtx.open(store, EP, run_id="run", rng_seed=7)
    result = await go(ctx, scenario(), Sim(turns, calls), Agent(calls, **agent_kw))
    return result, ctx


def shape(events):
    return [(e.seq, e.kind, e.actor, e.payload) for e in events]


async def journal(store):
    return await store.load(EP)


async def test_happy_path_journal():
    store = MemoryJournalStore()
    result, _ = await run(store, ["hi", "refund please"])
    j = await journal(store)
    assert [e.kind for e in j.events] == [
        "episode_started",
        "user_message",
        "agent_message",
        "user_message",
        "agent_message",
        "episode_ended",
    ]
    assert [e.seq for e in j.events] == list(range(6))
    assert result.outcome == "passed" and result.termination == "user_done"
    assert all(r.status == "done" for r in j.effects.values())
    assert set(j.effects) == {"llm:0", "llm:1", "llm:2", "target:0", "target:1"}


async def test_resume_from_every_crash_point_converges():
    turns = ["a", "b", "c"]
    clean = MemoryJournalStore()
    await run(clean, turns)
    expected = shape((await journal(clean)).events)

    for k in range(clean.appends):
        store, calls = MemoryJournalStore(), Counter()
        store.crash_before_append = k
        with pytest.raises(SimulatedCrash):
            await run(store, turns, calls)
        pending = {key for key, r in (await journal(store)).effects.items() if r.status != "done"}
        store.crash_before_append = None
        store.bump_epoch(EP)  # a new worker claims it
        result, ctx = await run(store, turns, calls)
        j = await journal(store)
        assert shape(j.events) == expected, f"crash point {k}"
        assert all(r.status == "done" for r in j.effects.values())
        assert result.outcome == "passed"
        # an effect runs once, or twice only if the crash caught it in flight
        assert max(calls.values()) <= 2
        assert sum(1 for c in calls.values() if c == 2) <= max(len(pending), 1)


async def test_completed_episode_replays_without_live_effects():
    store, calls = MemoryJournalStore(), Counter()
    await run(store, ["a"], calls)
    before = dict(calls)
    result, ctx = await run(store, ["a"], calls)
    assert calls == before and ctx.live_effects == 0
    assert result.outcome == "passed"


@settings(max_examples=60, deadline=None)
@given(
    turns=st.lists(st.text("abc", min_size=1, max_size=3), min_size=1, max_size=5, unique=True),
    crashes=st.lists(st.integers(0, 12), max_size=4),
)
async def test_property_any_crash_sequence_converges(turns, crashes):
    clean = MemoryJournalStore()
    await run(clean, turns)
    expected = shape((await journal(clean)).events)

    store = MemoryJournalStore()
    for extra in crashes:
        store.crash_before_append = store.appends + extra
        try:
            await run(store, turns)
        except SimulatedCrash:
            pass
        store.bump_epoch(EP)
    store.crash_before_append = None
    await run(store, turns)
    assert shape((await journal(store)).events) == expected


async def test_nondeterministic_reexecution_is_detected():
    store = MemoryJournalStore()
    store.crash_before_append = 5
    with pytest.raises(SimulatedCrash):
        await run(store, ["a", "b"])
    store.crash_before_append = None
    with pytest.raises(NonDeterminism):
        # the agent now receives a different message for the already-recorded target:0
        ctx = await EpisodeCtx.open(store, EP, run_id="run", rng_seed=7)
        calls = Counter()
        sim = Sim(["a", "b"], calls)
        agent = Agent(calls)
        original = agent.send
        agent.send = lambda c, t: original(c, t + "!")
        await go(ctx, scenario(), sim, agent)


async def test_stateful_target_in_flight_is_indeterminate():
    store, calls = MemoryJournalStore(), Counter()
    with pytest.raises(SimulatedCrash):
        await run(store, ["a", "b"], calls, stateful=True, die_on="b")
    assert (await journal(store)).effects["target:1"].status == "pending"
    with pytest.raises(IndeterminateEffect):
        await run(store, ["a", "b"], calls, stateful=True)


async def test_stateless_target_in_flight_is_retried():
    store, calls = MemoryJournalStore(), Counter()
    with pytest.raises(SimulatedCrash):
        await run(store, ["a", "b"], calls, die_on="b")
    result, _ = await run(store, ["a", "b"], calls)
    assert result.outcome == "passed" and calls["agent:b"] == 2 and calls["agent:a"] == 1


async def test_stale_lease_stops_the_old_worker():
    store = MemoryJournalStore()
    ctx = await EpisodeCtx.open(store, EP, run_id="run", rng_seed=7)
    store.bump_epoch(EP)  # someone else claimed it
    with pytest.raises(StaleLease):
        await go(ctx, scenario(), Sim(["a"], Counter()), Agent(Counter()))
    assert (await journal(store)).events == []


async def test_budget_exhaustion_ends_cleanly_and_is_recorded():
    store, ledger = MemoryJournalStore(), MemoryBudgetLedger(budget_usd_micros=250)
    ctx = await EpisodeCtx.open(store, EP, run_id="run", rng_seed=7, budget=ledger)
    result = await go(
        ctx, scenario(), Sim(["a", "b", "c", "d"], Counter(), cost=100), Agent(Counter())
    )
    assert result.outcome == "budget_exhausted" and result.termination == "budget"
    assert ledger.spent == 200 and ledger.reserved == 0
    j = await journal(store)
    assert j.events[-1].payload["outcome"] == "budget_exhausted"
    # replaying a finished episode costs nothing
    ctx2 = await EpisodeCtx.open(store, EP, run_id="run", rng_seed=7, budget=ledger)
    again = await go(
        ctx2, scenario(), Sim(["a", "b", "c", "d"], Counter(), cost=100), Agent(Counter())
    )
    assert again.outcome == "budget_exhausted" and ledger.spent == 200


async def test_target_error_is_recorded_and_replayed():
    store, calls = MemoryJournalStore(), Counter()
    result, _ = await run(store, ["a"], calls, reply=lambda t: TargetError("http_503", "down"))
    assert result.outcome == "target_error" and result.termination == "target_unreachable"
    again, ctx = await run(store, ["a"], calls, reply=lambda t: "should not be called")
    assert again.outcome == "target_error" and calls["agent:a"] == 1


async def test_max_turns_and_stuck_agent():
    store = MemoryJournalStore()
    ctx = await EpisodeCtx.open(store, EP, run_id="run", rng_seed=7)
    result = await go(ctx, scenario(max_turns=2), Sim(list("abcdef"), Counter()), Agent(Counter()))
    assert result.termination == "max_turns" and result.turns == 2

    store2 = MemoryJournalStore()
    result2, _ = await run(store2, list("abcdef"), reply=lambda t: "I cannot help with that.")
    assert result2.termination == "agent_stuck" and result2.turns == 3


async def test_strict_cassette_replay_is_exact():
    store = MemoryJournalStore()
    await run(store, ["a", "b"])
    original = await journal(store)
    cassette = dump_cassette(original, {"run": "r1"})

    replay_store = await store_from_cassette(cassette, EP)
    ctx = await EpisodeCtx.open(replay_store, EP, run_id="run", rng_seed=7, replay_only=True)
    calls = Counter()
    result = await go(ctx, scenario(), Sim(["a", "b"], calls), Agent(calls))
    assert not calls and result.outcome == "passed"
    assert shape((await journal(replay_store)).events) == shape(original.events)

    # a cassette that does not cover the run fails loudly in strict mode
    ctx2 = await EpisodeCtx.open(
        replay_store, "ep_other", run_id="run", rng_seed=7, replay_only=True
    )
    with pytest.raises(NonDeterminism):
        await go(ctx2, scenario(), Sim(["a"], calls), Agent(calls))


def test_redaction():
    out = redact(
        {
            "headers": {"Authorization": "Bearer abc"},
            "text": "key sk-live-123456 here",
            "nested": ["Bearer abcdefghijklmnopqrstuvwxyz"],
        },
        secrets=("sk-live-123456",),
    )
    assert out["headers"]["Authorization"] == "[REDACTED]"
    assert "sk-live-123456" not in out["text"]
    assert "abcdefghijklmnop" not in out["nested"][0]


async def test_rng_is_deterministic_across_executions():
    store = MemoryJournalStore()
    a = await EpisodeCtx.open(store, EP, run_id="r", rng_seed=1)
    b = await EpisodeCtx.open(store, EP, run_id="r", rng_seed=1)
    c = await EpisodeCtx.open(store, EP, run_id="r", rng_seed=2)
    xs, ys, zs = [a.random() for _ in range(3)], [b.random() for _ in range(3)], [c.random()]
    assert xs == ys and xs[0] != zs[0] and len(set(xs)) == 3
