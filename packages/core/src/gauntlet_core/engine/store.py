"""Store protocols and the in-memory implementations used by tests and local runs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from gauntlet_core.schema import EffectRecord, Event

from .errors import SeqConflict, StaleLease


@dataclass
class JournalSnapshot:
    events: list[Event] = field(default_factory=list)
    effects: dict[str, EffectRecord] = field(default_factory=dict)
    epoch: int = 0


class JournalStore(Protocol):
    async def load(self, episode_id: str) -> JournalSnapshot: ...

    async def append(
        self,
        episode_id: str,
        epoch: int,
        *,
        events: Sequence[Event] = (),
        effects: Sequence[EffectRecord] = (),
    ) -> None:
        """Atomically append events (seq must continue the journal) and upsert effects.

        Raises StaleLease if `epoch` is not the episode's current epoch, SeqConflict if the
        first event's seq is not the next free seq.
        """
        ...


class BudgetLedger(Protocol):
    async def reserve(self, run_id: str, usd_micros: int) -> bool: ...

    async def settle(self, run_id: str, reserved: int, actual: int) -> None: ...


class SimulatedCrash(BaseException):
    """Raised by MemoryJournalStore to simulate the process dying. BaseException on purpose:
    engine code that catches Exception must not be able to swallow a crash."""


class MemoryJournalStore:
    """In-memory journal. `crash_before_append=n` makes the n-th append (0-based) die
    before persisting anything, which is how tests explore every crash point."""

    def __init__(self) -> None:
        self._journals: dict[str, JournalSnapshot] = {}
        self.appends = 0
        self.crash_before_append: int | None = None

    def _get(self, episode_id: str) -> JournalSnapshot:
        return self._journals.setdefault(episode_id, JournalSnapshot())

    def bump_epoch(self, episode_id: str) -> int:
        """What EpisodeQueue.claim does: a new owner, a new fencing token."""
        j = self._get(episode_id)
        j.epoch += 1
        return j.epoch

    async def load(self, episode_id: str) -> JournalSnapshot:
        j = self._get(episode_id)
        return JournalSnapshot(list(j.events), dict(j.effects), j.epoch)

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
        j = self._get(episode_id)
        if epoch != j.epoch:
            raise StaleLease(f"{episode_id}: epoch {epoch} != {j.epoch}")
        if events and events[0].seq != len(j.events):
            raise SeqConflict(f"{episode_id}: seq {events[0].seq} != {len(j.events)}")
        j.events.extend(events)
        for e in effects:
            j.effects[e.key] = e
        self.appends += 1


class MemoryBudgetLedger:
    def __init__(self, budget_usd_micros: int | None = None) -> None:
        self.budget = budget_usd_micros
        self.reserved = 0
        self.spent = 0

    async def reserve(self, run_id: str, usd_micros: int) -> bool:
        if self.budget is not None and self.spent + self.reserved + usd_micros > self.budget:
            return False
        self.reserved += usd_micros
        return True

    async def settle(self, run_id: str, reserved: int, actual: int) -> None:
        self.reserved -= reserved
        self.spent += actual
