"""EpisodeCtx: the only door through which an episode touches the outside world.

Design (docs/plan/03-hard-cores.md section 1):

* Episode code is ordinary deterministic async code. Everything non-deterministic goes
  through `effect()`, whose result is recorded. Re-executing the same code over an existing
  journal returns recorded results, so a resumed episode converges on the same journal.
* Events are positional. `emit()` number i either matches journal event i (already
  persisted by a previous execution: verified and skipped) or is new (buffered). Buffered
  events are flushed atomically together with effect records.
* Randomness is counter-based on the episode seed, so it needs no recording.
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from gauntlet_core.schema import Cost, EffectKind, EffectRecord, Event, EventDraft, Json

from .errors import (
    BudgetExhausted,
    IndeterminateEffect,
    NonDeterminism,
    PermanentEffectError,
    TargetError,
)
from .redact import redact
from .store import BudgetLedger, JournalSnapshot, JournalStore

EffectFn = Callable[[], Awaitable[tuple[Json, Cost | None]]]

_ERROR_TYPES: dict[str, type[PermanentEffectError]] = {
    "TargetError": TargetError,
    "PermanentEffectError": PermanentEffectError,
}


def request_hash(request: Any) -> str:
    canonical = json.dumps(request, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


class EpisodeCtx:
    def __init__(
        self,
        *,
        episode_id: str,
        run_id: str,
        rng_seed: int,
        epoch: int,
        journal: JournalSnapshot,
        store: JournalStore,
        budget: BudgetLedger | None = None,
        secrets: tuple[str, ...] = (),
        replay_only: bool = False,
    ) -> None:
        self.episode_id = episode_id
        self.run_id = run_id
        self.rng_seed = rng_seed
        self.epoch = epoch
        self._store = store
        self._budget = budget
        self._secrets = secrets
        self._replay_only = replay_only  # strict cassette replay: a live effect is an error
        self._persisted: list[Event] = list(journal.events)
        self._effects: dict[str, EffectRecord] = dict(journal.effects)
        self._events: list[Event] = []  # events of this execution, in order (replayed + new)
        self._buffer: list[Event] = []  # new events not yet persisted
        self._ordinals: dict[str, int] = {}
        self._rng_n = 0
        self.live_effects = 0  # effects actually executed in this run (not replayed)
        self.spent = Cost()
        self.last_effect_ms = 0
        self.state: dict[str, Any] = {}  # scratch space for collaborators (world, target)
        # simulated clock: derived from the turn counter, never read from the wall
        self.clock_start = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
        self.clock_step_s = 60
        self.clock_jump_s = 0
        self.turn = 0

    def now(self) -> datetime:
        return self.clock_start + timedelta(
            seconds=self.turn * self.clock_step_s + self.clock_jump_s
        )

    @classmethod
    async def open(
        cls, store: JournalStore, episode_id: str, *, epoch: int | None = None, **kw: Any
    ) -> EpisodeCtx:
        journal = await store.load(episode_id)
        return cls(
            episode_id=episode_id,
            epoch=journal.epoch if epoch is None else epoch,
            journal=journal,
            store=store,
            **kw,
        )

    # ---------------------------------------------------------------- events

    @property
    def trajectory_so_far(self) -> Sequence[Event]:
        return self._events

    @property
    def replaying(self) -> bool:
        """True while this execution is still behind the persisted journal."""
        return len(self._events) < len(self._persisted)

    async def emit(self, *drafts: EventDraft) -> list[Event]:
        out: list[Event] = []
        for d in drafts:
            seq = len(self._events)
            if seq < len(self._persisted):
                recorded = self._persisted[seq]
                if recorded.kind != d.kind or recorded.actor != d.actor:
                    raise NonDeterminism(
                        f"{self.episode_id} seq {seq}: journal has {recorded.kind}/"
                        f"{recorded.actor}, execution produced {d.kind}/{d.actor}"
                    )
                ev = recorded
            else:
                data = d.model_dump()
                data["payload"] = redact(data["payload"], self._secrets)
                ev = Event(seq=seq, **data)
                self._buffer.append(ev)
            self._events.append(ev)
            out.append(ev)
        return out

    async def flush(self, effects: Sequence[EffectRecord] = ()) -> None:
        if not self._buffer and not effects:
            return
        events = list(self._buffer)
        await self._store.append(self.episode_id, self.epoch, events=events, effects=effects)
        # only after the append succeeded
        self._persisted.extend(events)
        del self._buffer[: len(events)]
        for e in effects:
            self._effects[e.key] = e

    # --------------------------------------------------------------- effects

    def _next_key(self, kind: str) -> str:
        n = self._ordinals.get(kind, 0)
        self._ordinals[kind] = n + 1
        return f"{kind}:{n}"

    async def effect(
        self,
        kind: EffectKind,
        request: Json,
        fn: EffectFn,
        *,
        retry_safe: bool,
        est_usd_micros: int = 0,
    ) -> Json:
        """Run `fn` at most once per journal (see module docstring) and return its result."""
        key = self._next_key(kind)
        rhash = request_hash(redact(request, self._secrets))
        rec = self._effects.get(key)

        if rec is not None:
            if rec.request_hash != rhash:
                raise NonDeterminism(
                    f"{self.episode_id} effect {key}: request differs from the recorded one"
                )
            if rec.status == "done":
                self.last_effect_ms = 0
                return rec.result or {}
            if rec.status == "failed":
                err = rec.result or {}
                cls = _ERROR_TYPES.get(err.get("type", ""), PermanentEffectError)
                raise cls(err.get("code", "error"), err.get("message", ""))
            if not retry_safe:  # pending, and we cannot know whether it happened
                raise IndeterminateEffect(f"{self.episode_id} effect {key}")
        elif self._replay_only:
            raise NonDeterminism(f"{self.episode_id} effect {key}: not in cassette")

        reserved = 0
        if self._budget is not None and est_usd_micros > 0:
            if not await self._budget.reserve(self.run_id, est_usd_micros):
                raise BudgetExhausted(self.run_id)
            reserved = est_usd_micros

        actual = 0
        try:
            if rec is None:
                pending = EffectRecord(key=key, kind=kind, request_hash=rhash, status="pending")
                await self.flush([pending])
            started = time.perf_counter()
            try:
                result, cost = await fn()
            except PermanentEffectError as exc:
                failed = EffectRecord(
                    key=key,
                    kind=kind,
                    request_hash=rhash,
                    status="failed",
                    result={"type": type(exc).__name__, "code": exc.code, "message": exc.message},
                )
                await self.flush([failed])
                raise
            self.last_effect_ms = int((time.perf_counter() - started) * 1000)
            self.live_effects += 1
            actual = cost.usd_micros if cost else 0
            if cost:
                self.spent = self.spent + cost
            done = EffectRecord(
                key=key,
                kind=kind,
                request_hash=rhash,
                status="done",
                result=redact(result, self._secrets),
                cost=cost,
            )
            await self.flush([done])
            return done.result or {}
        finally:
            if reserved and self._budget is not None:
                await self._budget.settle(self.run_id, reserved, actual)

    # ------------------------------------------------------------ randomness

    def random(self) -> float:
        """Deterministic per (episode seed, call index). Needs no journal record."""
        n = self._rng_n
        self._rng_n += 1
        return random.Random(f"{self.rng_seed}:{self.episode_id}:{n}").random()
