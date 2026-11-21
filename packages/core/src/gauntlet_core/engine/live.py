"""The `agent_live` half of EpisodeCtx (hard-cores 1.6a): staying in sync with a recording,
detecting the first divergence, and going live from there."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from gauntlet_core.schema import EffectRecord, Event, EventDraft, Json

from .errors import PermanentEffectError, TargetError
from .redact import redact
from .replay import is_recorded
from .store import JournalStore

_ERROR_TYPES: dict[str, type[PermanentEffectError]] = {
    "TargetError": TargetError,
    "PermanentEffectError": PermanentEffectError,
}


def ordinal(key: str) -> int:
    return int(key.partition(":")[2])


def is_diverged_note(ev: Event) -> bool:
    return ev.kind == "sim_note" and ev.payload.get("kind") == "diverged"


def canonical(value: Any) -> Any:
    """Recursively sort dict keys: an effect result must look the same live and replayed
    (Postgres `jsonb` reorders keys), or anything hashing it differs after a resume."""
    if isinstance(value, dict):
        return {k: canonical(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return [canonical(v) for v in value]
    return value


class AgentLiveMixin:
    # state owned by EpisodeCtx
    episode_id: str
    epoch: int
    last_effect_ms: int
    _store: JournalStore
    _secrets: tuple[str, ...]
    _persisted: list[Event]
    _effects: dict[str, EffectRecord]
    _events: list[Event]
    _ordinals: dict[str, int]
    _diverged: bool
    _top: dict[str, int]
    _recorded: dict[str, list[str]]
    _reserved: set[str]
    _has_recording: bool

    def now(self) -> datetime: ...

    async def flush(self, effects: Sequence[EffectRecord] = ()) -> None: ...

    @property
    def diverged(self) -> bool:
        return self._diverged

    def _absorb_note(self) -> None:
        """The journal already holds the divergence note at our position (a resume): adopt it."""
        if self._diverged:
            return
        pos = len(self._events)
        if pos < len(self._persisted) and is_diverged_note(self._persisted[pos]):
            self._events.append(self._persisted[pos])
            self._diverged = True

    async def _agent_live_emit_check(self, d: EventDraft) -> None:
        """While in sync, an event must equal the recorded one at its position (kind, actor,
        payload); the first difference is divergence."""
        self._absorb_note()
        if self._diverged:
            return
        seq = len(self._events)
        if seq < len(self._persisted):
            rec = self._persisted[seq]
            same = (
                rec.kind == d.kind
                and rec.actor == d.actor
                and rec.payload == redact(d.model_dump()["payload"], self._secrets)
            )
            if same:
                return
        elif not self._has_recording:
            return  # nothing to be in sync with (an empty or abandoned journal): plain live
        await self._diverge(f"event:{seq}")

    async def _diverge(self, note: str) -> None:
        """Leave the recording: drop its unconsumed tail, record one `diverged` sim_note at the
        current position (atomically with the drop), and run live from here on."""
        if self._diverged:
            return
        await self.flush()  # nothing is buffered while in sync; defensive
        pos = len(self._events)
        unconsumed = [
            key for kind, keys in self._recorded.items() for key in keys[self._top.get(kind, 0) :]
        ]
        ev = Event(
            seq=pos,
            kind="sim_note",
            actor="platform",
            sim_time=self.now(),
            payload={"kind": "diverged", "note": note, "first_live_seq": pos},
        )
        await self._store.replace_tail(
            self.episode_id, self.epoch, from_seq=pos, drop_effects=unconsumed, events=[ev]
        )
        del self._persisted[pos:]
        self._persisted.append(ev)
        for key in unconsumed:
            self._effects.pop(key, None)
            self._reserved.discard(key)
        self._events.append(ev)
        self._diverged = True

    async def _replay_recorded(self, kind: str, rhash: str) -> Json | None:
        """Top-level effect while in sync: the next recorded effect of this kind if its request
        matches (returns the recorded result, raising a recorded failure), else diverge and
        return None (the caller then runs the effect live)."""
        i = self._top.get(kind, 0)
        keys = self._recorded.get(kind, [])
        if i >= len(keys):
            if self._has_recording:
                await self._diverge(f"{kind}:{i} past the recording")
            return None
        rec = self._effects[keys[i]]
        if rec.request_hash != rhash:
            await self._diverge(rec.key)
            return None
        self._top[kind] = i + 1
        self._ordinals[kind] = max(self._ordinals.get(kind, 0), ordinal(rec.key) + 1)
        self.last_effect_ms = 0
        if rec.status == "failed":
            err = rec.result or {}
            cls = _ERROR_TYPES.get(err.get("type", ""), PermanentEffectError)
            raise cls(err.get("code", "error"), err.get("message", ""))
        return canonical(rec.result or {})

    async def _rollback_nested(self) -> None:
        """A live `target` effect was pending when the worker died. Its nested records cannot
        be attributed, but in agent_live mode the target is re-run live anyway, so delete the
        crashed attempt's nested effects and events and run it again."""
        own = [
            key
            for key, rec in self._effects.items()
            if not is_recorded(rec) and ordinal(key) >= self._ordinals.get(rec.kind, 0)
        ]
        pos = len(self._events)
        notes = [
            i for i in range(pos, len(self._persisted)) if is_diverged_note(self._persisted[i])
        ]
        from_seq = notes[0] if notes else len(self._persisted)
        if not own and from_seq >= len(self._persisted):
            return
        await self._store.replace_tail(
            self.episode_id, self.epoch, from_seq=from_seq, drop_effects=own
        )
        del self._persisted[from_seq:]
        for key in own:
            self._effects.pop(key, None)
