"""EpisodeCtx: the only door through which an episode touches the outside world.

Design (docs/plan/03-hard-cores.md section 1):

* Episode code is ordinary deterministic async code. Everything non-deterministic goes
  through `effect()`, whose result is recorded. Re-executing the same code over an existing
  journal returns recorded results, so a resumed episode converges on the same journal.
* Events are positional. `emit()` number i either matches journal event i (already
  persisted by a previous execution: verified and skipped) or is new (buffered). Buffered
  events are flushed atomically together with effect records.
* Randomness is counter-based on the episode seed, so it needs no recording.
* Effects can nest (a wired agent calling the facade, an `llm_sim` tool). The outer effect
  records a *span* (events and per-kind effect ordinals produced inside it); replaying the
  outer effect advances the cursors by the span and tells the replay hooks about the events
  (docs/plan/03-hard-cores.md section 1.7a).
* `mode="agent_live"` replays a recording against a new agent version (section 1.6a): the
  copied top-level effects (simulator, judges) replay by *position among top-level effects of
  their kind* while the recording keeps matching; `target` effects and everything nested in
  them run live; the first mismatch drops the rest of the recording and goes live (`_diverge`).
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from gauntlet_core.schema import Cost, EffectKind, EffectRecord, Event, EventDraft, Json

from .errors import (
    BudgetExhausted,
    EngineError,
    IndeterminateEffect,
    NonDeterminism,
    PermanentEffectError,
    TargetError,
)
from .live import AgentLiveMixin, canonical, is_diverged_note, ordinal
from .redact import redact
from .replay import is_recorded
from .store import BudgetLedger, JournalSnapshot, JournalStore

EffectFn = Callable[[], Awaitable[tuple[Json, Cost | None]]]
ReplayHook = Callable[[Sequence[Event]], None]
Mode = Literal["live", "strict", "agent_live"]

_ERROR_TYPES: dict[str, type[PermanentEffectError]] = {
    "TargetError": TargetError,
    "PermanentEffectError": PermanentEffectError,
}


@dataclass
class _Frame:
    """An in-flight effect: where the event cursor and the ordinals stood when it started."""

    key: str
    ev0: int
    ord0: dict[str, int]


def request_hash(request: Any) -> str:
    canonical = json.dumps(request, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


class EpisodeCtx(AgentLiveMixin):
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
        mode: Mode = "live",
        verify_payloads: bool = False,
        clock_start: datetime | None = None,
    ) -> None:
        self.episode_id = episode_id
        self.run_id = run_id
        self.rng_seed = rng_seed
        self.epoch = epoch
        self._store = store
        self._budget = budget
        self._secrets = secrets
        self.mode: Mode = "strict" if replay_only else mode
        self._verify_payloads = verify_payloads  # replay checks event payloads, not just kinds
        self._replay_only = self.mode == "strict"  # a live effect is an error
        self._agent_live = self.mode == "agent_live"
        self._diverged = False
        self._top: dict[str, int] = {}  # agent_live: recorded top-level effects consumed per kind
        self._persisted: list[Event] = list(journal.events)
        self._effects: dict[str, EffectRecord] = dict(journal.effects)
        self._events: list[Event] = []  # events of this execution, in order (replayed + new)
        self._buffer: list[Event] = []  # new events not yet persisted
        self._ordinals: dict[str, int] = {}
        self._stack: list[_Frame] = []  # effects in flight, outermost first
        self._hooks: list[ReplayHook] = []
        self._rng_n = 0
        self._recorded: dict[str, list[str]] = {}  # agent_live: kind -> recorded keys, in order
        self._reserved: set[str] = set()  # agent_live: keys live effects must not take
        if self._agent_live:
            for key, rec in sorted(self._effects.items(), key=lambda kv: ordinal(kv[0])):
                if is_recorded(rec):
                    self._recorded.setdefault(rec.kind, []).append(key)
                    self._reserved.add(key)
        self._has_recording = bool(self._reserved)
        self.live_effects = 0  # effects actually executed in this run (not replayed)
        self.spent = Cost()
        self.last_effect_ms = 0
        self.state: dict[str, Any] = {}  # scratch space for collaborators (world, target)
        # simulated clock: derived from the turn counter, never read from the wall
        self.clock_start = clock_start or datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
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
            if self._agent_live:
                await self._agent_live_emit_check(d)
            seq = len(self._events)
            if seq < len(self._persisted):
                recorded = self._persisted[seq]
                if recorded.kind != d.kind or recorded.actor != d.actor:
                    raise NonDeterminism(
                        f"{self.episode_id} seq {seq}: journal has {recorded.kind}/"
                        f"{recorded.actor}, execution produced {d.kind}/{d.actor}",
                        seq=seq,
                        expected={"kind": recorded.kind, "actor": recorded.actor},
                        got={"kind": d.kind, "actor": d.actor},
                    )
                if self._verify_payloads:
                    got = redact(d.model_dump()["payload"], self._secrets)
                    if got != recorded.payload:
                        raise NonDeterminism(
                            f"{self.episode_id} seq {seq}: {d.kind} payload differs",
                            seq=seq,
                            expected=recorded.payload,
                            got=got,
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

    # ---------------------------------------------------------- nested effects

    def add_replay_hook(self, hook: ReplayHook) -> None:
        """`hook(events)` is called with events this execution did not emit itself: those
        skipped by replaying an outer effect's span, and those another process appended
        during an outer effect. `World.bind` registers one that re-applies tool patches."""
        if hook not in self._hooks:
            self._hooks.append(hook)

    @property
    def effect_depth(self) -> int:
        return len(self._stack)

    def seek_end(self) -> None:
        """Position this ctx after everything already journaled (used by the api facade, which
        opens a fresh ctx per request). Replay hooks see all existing events."""
        self._events = list(self._persisted)
        self._buffer.clear()
        counts: dict[str, int] = {}
        for key in self._effects:
            kind, _, n = key.partition(":")
            counts[kind] = max(counts.get(kind, 0), int(n) + 1)
        self._ordinals = counts
        self.turn = sum(1 for e in self._events if e.kind == "agent_message")
        if self._events:
            self._run_hooks(self._events)

    def _run_hooks(self, events: Sequence[Event]) -> None:
        for hook in self._hooks:
            hook(events)

    def _replay_span(self, rec: EffectRecord) -> None:
        span = rec.span
        if not span:
            return
        n = int(span.get("events", 0))
        start = len(self._events)
        skipped = self._persisted[start : start + n]
        if len(skipped) != n:
            raise NonDeterminism(f"{self.episode_id} effect {rec.key}: span events missing")
        self._events.extend(skipped)
        if self._agent_live and any(is_diverged_note(e) for e in skipped):
            self._diverged = True
        for kind, count in (span.get("ordinals") or {}).items():
            self._ordinals[kind] = self._ordinals.get(kind, 0) + int(count)
        if skipped:
            self._run_hooks(skipped)

    def _has_nested_records(self) -> bool:
        """Journal content beyond this execution's position: work done inside a pending outer
        effect that this execution cannot attribute to anything."""
        if len(self._persisted) > len(self._events):
            return True
        for key in self._effects:
            kind, _, n = key.partition(":")
            if int(n) >= self._ordinals.get(kind, 0):
                return True
        return False

    async def _absorb_external(self) -> None:
        """Reload the journal tail: another process (the api facade) appended nested events and
        effects while the outer effect was in flight. Adopt them and tell the hooks."""
        snap = await self._store.load(self.episode_id)
        ext = snap.events[len(self._persisted) :]
        if ext:
            if self._buffer:
                raise EngineError(f"{self.episode_id}: journal appended by two writers at once")
            self._persisted.extend(ext)
            self._events.extend(ext)
        for key, rec in snap.effects.items():
            if key not in self._effects:
                self._effects[key] = rec
                kind, _, n = key.partition(":")
                self._ordinals[kind] = max(self._ordinals.get(kind, 0), int(n) + 1)
        if ext:
            self._run_hooks(ext)

    async def _close_span(self, frame: _Frame, nested: bool) -> Json | None:
        if nested:
            await self._absorb_external()
        events = len(self._events) - frame.ev0
        ordinals = {
            k: n - frame.ord0.get(k, 0)
            for k, n in self._ordinals.items()
            if n > frame.ord0.get(k, 0)
        }
        if not (events or ordinals):
            return None
        # `start`: the first ordinal of each kind that ran inside, so a fork never has to infer it
        start = {k: frame.ord0.get(k, 0) for k in ordinals}
        return {"events": events, "ordinals": ordinals, "start": start}

    # --------------------------------------------------------------- effects

    def _next_key(self, kind: str) -> str:
        n = self._ordinals.get(kind, 0)
        while f"{kind}:{n}" in self._reserved:  # agent_live: a recorded effect owns this key
            n += 1
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
        nested: bool = False,
    ) -> Json:
        """Run `fn` at most once per journal (see module docstring) and return its result.

        `nested=True` says other processes may append nested work to this episode while `fn`
        runs (a wired agent calling the api facade): the journal tail is reloaded afterwards.
        """
        rhash = request_hash(redact(request, self._secrets))
        if self._agent_live and kind != "target" and not self._stack:
            self._absorb_note()  # a live target effect may own a note at this position
            if not self._diverged:
                replayed = await self._replay_recorded(kind, rhash)
                if replayed is not None:
                    return replayed
        key = self._next_key(kind)
        rec = self._effects.get(key)

        if rec is not None:
            if rec.request_hash != rhash:
                raise NonDeterminism(
                    f"{self.episode_id} effect {key}: request differs from the recorded one",
                    seq=len(self._events),
                    expected=rec.request_hash,
                    got=rhash,
                )
            if rec.status == "done":
                self.last_effect_ms = 0
                self._replay_span(rec)
                return canonical(rec.result or {})
            if rec.status == "failed":
                self._replay_span(rec)
                err = rec.result or {}
                cls = _ERROR_TYPES.get(err.get("type", ""), PermanentEffectError)
                raise cls(err.get("code", "error"), err.get("message", ""))
            if self._agent_live and kind == "target" and retry_safe:
                await self._rollback_nested()  # the target always runs live: redo it cleanly
            elif self._has_nested_records():  # 1.7a: nested work cannot be re-attributed
                raise IndeterminateEffect(f"{self.episode_id} effect {key}: nested work recorded")
            if not retry_safe:  # pending, and we cannot know whether it happened
                raise IndeterminateEffect(f"{self.episode_id} effect {key}")
        elif self._replay_only:
            raise NonDeterminism(
                f"{self.episode_id} effect {key}: not in cassette",
                seq=len(self._events),
                expected=None,
                got=rhash,
            )

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
            frame = _Frame(key, len(self._events), dict(self._ordinals))
            self._stack.append(frame)
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
                    span=await self._close_span(frame, nested),
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
                span=await self._close_span(frame, nested),
            )
            await self.flush([done])
            return canonical(done.result or {})
        finally:
            if self._stack and self._stack[-1].key == key:
                self._stack.pop()
            if reserved and self._budget is not None:
                await self._budget.settle(self.run_id, reserved, actual)

    # ------------------------------------------------------------ randomness

    def random(self, index: int | None = None) -> float:
        """Deterministic per (episode seed, call index). Needs no journal record. Pass an
        explicit `index` when the caller has its own stable counter (the world's call number),
        so processes that did not run every earlier call still draw the same value."""
        n = self._rng_n if index is None else index
        if index is None:
            self._rng_n += 1
        return random.Random(f"{self.rng_seed}:{self.episode_id}:{n}").random()
