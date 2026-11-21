"""agent_live replay (hard-cores 1.6a, 1.7a) on every JournalStore backend."""

from __future__ import annotations

from collections import Counter

import pytest
from gauntlet_core.engine import (
    EpisodeCtx,
    MemoryJournalStore,
    SimTurn,
    SimulatedCrash,
    fork_for_agent_live,
    run_episode,
)
from gauntlet_core.schema import Cost, EventDraft
from harness import T0, Agent, CrashingStore, Harness, NestedAgent, effect_shape, scenario, shape

TURNS = ["a", "b", "c", "d"]
SRC, NEW = "ep_src", "ep_new"


class CSim:
    """Scripted simulator that counts how often its llm effect really runs."""

    def __init__(self, turns: list[str], calls: Counter[str]) -> None:
        self.turns, self.calls = turns, calls

    async def next_message(self, ctx: EpisodeCtx) -> SimTurn:
        n = sum(1 for e in ctx.trajectory_so_far if e.kind == "user_message")

        async def fn():
            self.calls["sim"] += 1
            return {"text": self.turns[n] if n < len(self.turns) else None}, Cost(usd_micros=5)

        res = await ctx.effect("llm", {"turn": n}, fn, retry_safe=True, est_usd_micros=5)
        return SimTurn("message", res["text"]) if res["text"] is not None else SimTurn("done")


class Changed(Agent):
    """Replies differently once it sees `trigger`."""

    def __init__(self, calls: Counter[str], trigger: str) -> None:
        super().__init__(calls)
        self.trigger = trigger

    async def send(self, ctx: EpisodeCtx, user_text: str) -> str:
        async def fn():
            self.calls["agent"] += 1
            return {"reply": "other" if user_text == self.trigger else f"re: {user_text}"}, None

        return (await ctx.effect("target", {"text": user_text}, fn, retry_safe=True))["reply"]


class LlmAgent(Agent):
    """Nested llm effects inside the target effect (a hosted agent's model calls)."""

    def __init__(self, calls: Counter[str], inner: int) -> None:
        super().__init__(calls)
        self.inner = inner

    async def send(self, ctx: EpisodeCtx, user_text: str) -> str:
        async def fn():
            self.calls["agent"] += 1

            async def model():
                return {"o": 1}, Cost(usd_micros=1)

            for i in range(self.inner):
                await ctx.effect("llm", {"agent": user_text, "i": i}, model, retry_safe=True)
            return {"reply": f"re: {user_text}"}, None

        return (await ctx.effect("target", {"text": user_text}, fn, retry_safe=True))["reply"]


async def record(backend: Harness, agent: Agent, ep: str = SRC) -> None:
    await backend.new_episode(ep)
    ctx = await EpisodeCtx.open(backend.store, ep, run_id="run_c", rng_seed=7)
    res = await run_episode(ctx, scenario(), agent, CSim(TURNS, Counter()))
    assert res.outcome == "passed"


async def replay(store, agent: Agent, calls: Counter[str], ep: str = NEW, turns=TURNS):
    ctx = await EpisodeCtx.open(
        store, ep, run_id="run_c", rng_seed=7, mode="agent_live", budget=None
    )
    return await run_episode(ctx, scenario(), agent, CSim(turns, calls))


def notes(events) -> list[int]:
    return [e.seq for e in events if e.kind == "sim_note" and e.payload.get("kind") == "diverged"]


def transcript(events) -> list[tuple[str, str]]:
    return [(e.kind, e.payload.get("text", "")) for e in events if "message" in e.kind]


@pytest.mark.parametrize("agent_cls", [Agent, NestedAgent], ids=["plain", "nested"])
async def test_identical_agent_makes_zero_live_simulator_calls(backend: Harness, agent_cls):
    await record(backend, agent_cls(Counter()))
    src = await backend.store.load(SRC)
    await backend.new_episode(NEW)
    await fork_for_agent_live(backend.store, SRC, NEW)
    calls: Counter[str] = Counter()
    res = await replay(backend.store, agent_cls(calls), calls)
    j = await backend.store.load(NEW)
    assert res.outcome == "passed"
    assert calls["sim"] == 0  # the simulator was never called
    assert sum(calls[t] for t in TURNS) == 4  # the agent ran live every turn
    assert notes(j.events) == []
    assert shape(j.events) == shape(src.events)  # identical transcript, event for event


async def test_fork_discards_target_effects_and_costs(backend: Harness):
    await record(backend, NestedAgent(Counter()))
    await backend.new_episode(NEW)
    await fork_for_agent_live(backend.store, SRC, NEW)
    j = await backend.store.load(NEW)
    assert {r.kind for r in j.effects.values()} == {"llm"}  # no target, no nested tool
    assert all(r.cost is None for r in j.effects.values())
    assert j.epoch == 0 and len(j.events) == len((await backend.store.load(SRC)).events)


@pytest.mark.parametrize("inner", [1, 2, 4])
async def test_nested_effect_count_change_does_not_shift_the_simulator(backend: Harness, inner):
    await record(backend, LlmAgent(Counter(), inner=2))
    await backend.new_episode(NEW)
    await fork_for_agent_live(backend.store, SRC, NEW)
    calls: Counter[str] = Counter()
    await replay(backend.store, LlmAgent(calls, inner=inner), calls)
    j = await backend.store.load(NEW)
    assert calls["sim"] == 0 and notes(j.events) == []
    assert len({r.key for r in j.effects.values()}) == len(j.effects)


async def test_reply_change_at_turn_k_replays_before_and_goes_live_after(backend: Harness):
    await record(backend, Agent(Counter()))
    src = await backend.store.load(SRC)
    await backend.new_episode(NEW)
    await fork_for_agent_live(backend.store, SRC, NEW)
    calls: Counter[str] = Counter()
    # turn index 1 ("b") gets a different reply; the simulator then continues live
    res = await replay(
        backend.store, Changed(calls, "b"), calls, turns=["a", "b", "c2", "d2", "e2"]
    )
    j = await backend.store.load(NEW)
    assert res.outcome == "passed"
    assert calls["sim"] == 4  # turns 2, 3, 4 and the final "done" are live; 0 and 1 replayed
    (note_seq,) = notes(j.events)
    # the note sits exactly where the recording stopped matching: before agent_message #1
    recorded_reply_seq = [e.seq for e in src.events if e.kind == "agent_message"][1]
    assert note_seq == recorded_reply_seq
    note = j.events[note_seq]
    assert note.payload["kind"] == "diverged" and note.payload["first_live_seq"] == note_seq
    assert shape(j.events[:note_seq]) == shape(src.events[:note_seq])
    assert j.events[note_seq + 1].payload == {"text": "other"}
    assert transcript(j.events)[-2:] == [("user_message", "e2"), ("agent_message", "re: e2")]
    # no stale tail: dense seqs, and no recorded effect past the divergence survived
    assert [e.seq for e in j.events] == list(range(len(j.events)))
    assert all(r.status == "done" for r in j.effects.values())


async def test_simulator_request_change_is_divergence_not_nondeterminism(backend: Harness):
    """Identical agent, but the judge-ish top-level llm effect asks something else."""
    await record(backend, Agent(Counter()))
    await backend.new_episode(NEW)
    await fork_for_agent_live(backend.store, SRC, NEW)

    class OtherSim(CSim):
        async def next_message(self, ctx: EpisodeCtx) -> SimTurn:
            n = sum(1 for e in ctx.trajectory_so_far if e.kind == "user_message")

            async def fn():
                self.calls["sim"] += 1
                return {"text": self.turns[n] if n < len(self.turns) else None}, None

            req = {"turn": n} if n < 2 else {"turn": n, "v": 2}
            res = await ctx.effect("llm", req, fn, retry_safe=True)
            return SimTurn("message", res["text"]) if res["text"] is not None else SimTurn("done")

    calls: Counter[str] = Counter()
    ctx = await EpisodeCtx.open(backend.store, NEW, run_id="run_c", rng_seed=7, mode="agent_live")
    await run_episode(ctx, scenario(), Agent(calls), OtherSim(TURNS, calls))
    j = await backend.store.load(NEW)
    (note_seq,) = notes(j.events)
    assert j.events[note_seq].payload["note"].startswith("llm:")
    assert calls["sim"] == 3  # turns 2, 3 and "done" live


async def test_agent_live_crash_resume_converges(backend: Harness):
    """Crash before every append of an agent_live episode (changed agent), resume, and the
    journal equals the one an uninterrupted run produces."""
    await record(backend, NestedAgent(Counter()))
    turns = ["a", "b", "c2", "d2"]

    class NestedChanged(NestedAgent):
        async def send(self, ctx, user_text):
            async def fn():
                self.calls[user_text] += 1

                async def inner():
                    return {"v": user_text}, None

                await ctx.effect("tool", {"t": user_text}, inner, retry_safe=True)
                await ctx.emit(
                    EventDraft(
                        kind="sim_note",
                        actor="platform",
                        sim_time=T0,
                        payload={"n": "x" + user_text if user_text == "b" else user_text},
                    )
                )
                return {"reply": f"re: {user_text}"}, None

            return (await ctx.effect("target", {"text": user_text}, fn, retry_safe=True))["reply"]

    # reference: an uninterrupted agent_live run on an in-memory copy of the recording
    ref = CrashingStore(MemoryJournalStore())
    src_snap = await backend.store.load(SRC)
    await ref.inner.append(SRC, 0, events=src_snap.events, effects=list(src_snap.effects.values()))
    await fork_for_agent_live(ref, SRC, NEW)
    await replay(ref, NestedChanged(Counter()), Counter(), turns=turns)
    expected = await ref.load(NEW)
    assert len(notes(expected.events)) == 1
    for k in range(ref.appends):
        ep = f"ep_crash_{k}"
        await backend.new_episode(ep)
        await fork_for_agent_live(backend.store, SRC, ep)
        calls: Counter[str] = Counter()
        crashing = CrashingStore(backend.store, crash_before_append=k)
        try:
            await replay(crashing, NestedChanged(calls), calls, ep=ep, turns=turns)
        except SimulatedCrash:
            await backend.claim(ep)
            await replay(backend.store, NestedChanged(calls), calls, ep=ep, turns=turns)
        j = await backend.store.load(ep)
        assert shape(j.events) == shape(expected.events), f"crash point {k}"
        assert effect_shape(j) == effect_shape(expected), f"crash point {k}"
        assert len(notes(j.events)) == 1, f"crash point {k}"
        assert j.attempt == 0, f"crash point {k}"
