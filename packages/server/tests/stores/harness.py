"""Backend harness for the parametrised store contract suite, plus a tiny engine fixture.

A harness wraps one JournalStore implementation and the two things the contract needs that
the protocol does not have: creating an episode and claiming it (bumping its epoch).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from gauntlet_core.engine import (
    EpisodeCtx,
    JournalSnapshot,
    JournalStore,
    MemoryJournalStore,
    SimTurn,
    SimulatedCrash,
    SqliteJournalStore,
)
from gauntlet_core.schema import Cost, EffectRecord, Event, EventDraft, Scenario
from gauntlet_server.db import Sessionmaker
from gauntlet_server.stores import PgJournalStore
from pg_helpers import add_episode, add_run, execute, scalar

T0 = datetime(2026, 1, 1, tzinfo=UTC)


class Harness(Protocol):
    store: JournalStore

    async def new_episode(self, episode_id: str) -> None: ...

    async def claim(self, episode_id: str) -> int:
        """What EpisodeQueue.claim does to the journal: epoch + 1. Returns the new epoch."""
        ...


class MemoryHarness:
    def __init__(self) -> None:
        self.mem = MemoryJournalStore()
        self.store: JournalStore = self.mem

    async def new_episode(self, episode_id: str) -> None:
        pass

    async def claim(self, episode_id: str) -> int:
        return self.mem.bump_epoch(episode_id)


class SqliteHarness:
    def __init__(self, store: SqliteJournalStore) -> None:
        self.sqlite = store
        self.store: JournalStore = store

    async def new_episode(self, episode_id: str) -> None:
        pass

    async def claim(self, episode_id: str) -> int:
        return await self.sqlite.bump_epoch(episode_id)


class PgHarness:
    def __init__(self, sm: Sessionmaker) -> None:
        self.sm = sm
        self.store: JournalStore = PgJournalStore(sm)
        self._run = False

    async def new_episode(self, episode_id: str) -> None:
        if not self._run:
            await add_run(self.sm, "run_c")
            self._run = True
        await add_episode(self.sm, episode_id, "run_c")

    async def claim(self, episode_id: str) -> int:
        await execute(
            self.sm, "UPDATE episodes SET epoch = epoch + 1 WHERE id = :id", id=episode_id
        )
        return int(
            await scalar(self.sm, "SELECT epoch FROM episodes WHERE id = :id", id=episode_id)
        )


class CrashingStore:
    """Wraps any store; dies (SimulatedCrash) instead of performing append number
    `crash_before_append`, and counts completed appends."""

    def __init__(self, inner: JournalStore, crash_before_append: int | None = None) -> None:
        self.inner, self.crash_before_append, self.appends = inner, crash_before_append, 0

    async def load(self, episode_id: str) -> JournalSnapshot:
        return await self.inner.load(episode_id)

    async def append(
        self,
        episode_id: str,
        epoch: int,
        *,
        events: Sequence[Event] = (),
        effects: Sequence[EffectRecord] = (),
    ) -> None:
        if self.crash_before_append is not None and self.appends >= self.crash_before_append:
            raise SimulatedCrash
        await self.inner.append(episode_id, epoch, events=events, effects=effects)
        self.appends += 1

    async def abandon_attempt(self, episode_id: str, epoch: int) -> int:
        return await self.inner.abandon_attempt(episode_id, epoch)


def event(seq: int, kind: str = "user_message", **payload: Any) -> Event:
    return Event(
        seq=seq,
        kind=kind,  # type: ignore[arg-type]
        actor="user",
        sim_time=T0,
        payload=payload or {"text": f"m{seq}"},
    )


def effect(key: str, status: str = "done", cost: int | None = None, **result: Any) -> EffectRecord:
    return EffectRecord(
        key=key,
        kind=key.split(":")[0],  # type: ignore[arg-type]
        request_hash="h-" + key,
        status=status,  # type: ignore[arg-type]
        result=result or None,
        cost=Cost(usd_micros=cost, input_tokens=0, output_tokens=0, model=None) if cost else None,
    )


def shape(events: Sequence[Event]) -> list[tuple[Any, ...]]:
    return [(e.seq, e.kind, e.actor, e.payload) for e in events]


def effect_shape(j: JournalSnapshot) -> dict[str, tuple[Any, ...]]:
    return {k: (r.kind, r.status, r.request_hash, r.result, r.span) for k, r in j.effects.items()}


# ----------------------------------------------------------------- tiny engine fixture


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
    def __init__(self, turns: list[str]) -> None:
        self.turns = turns

    async def next_message(self, ctx: EpisodeCtx) -> SimTurn:
        n = sum(1 for e in ctx.trajectory_so_far if e.kind == "user_message")

        async def fn():
            return {"text": self.turns[n] if n < len(self.turns) else None}, Cost(usd_micros=5)

        res = await ctx.effect("llm", {"turn": n}, fn, retry_safe=True, est_usd_micros=5)
        return SimTurn("message", res["text"]) if res["text"] is not None else SimTurn("done")


class Agent:
    stateful = False

    def __init__(self, calls: Counter[str]) -> None:
        self.calls = calls

    async def open(self, ctx: EpisodeCtx) -> None:
        pass

    async def close(self, ctx: EpisodeCtx) -> None:
        pass

    async def send(self, ctx: EpisodeCtx, user_text: str) -> str:
        async def fn():
            self.calls[user_text] += 1
            return {"reply": f"re: {user_text}"}, None

        res = await ctx.effect("target", {"text": user_text}, fn, retry_safe=True)
        return res["reply"]


class NestedAgent(Agent):
    """The outer `target` effect does nested work: a `tool` effect and an event (1.7a)."""

    async def send(self, ctx: EpisodeCtx, user_text: str) -> str:
        async def fn():
            self.calls[user_text] += 1

            async def inner():
                return {"v": user_text}, None

            await ctx.effect("tool", {"t": user_text}, inner, retry_safe=True)
            await ctx.emit(
                EventDraft(kind="sim_note", actor="platform", sim_time=T0, payload={"n": user_text})
            )
            return {"reply": f"re: {user_text}"}, None

        res = await ctx.effect("target", {"text": user_text}, fn, retry_safe=True)
        return res["reply"]
