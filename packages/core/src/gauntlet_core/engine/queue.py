"""Episode leases and the queue protocol (contracts section 3, CQ-B10) plus a memory queue.

The Postgres implementation lives in gauntlet_server. Both obey the same rules: `claim`
bumps the fencing epoch, only the current epoch may heartbeat, finish or append, and an
expired lease can be reclaimed by anyone.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from gauntlet_core.schema import Outcome, Termination

from .errors import StaleLease
from .store import MemoryJournalStore

__all__ = ["EpisodeLease", "EpisodeQueue", "MemoryEpisodeQueue"]


@dataclass(frozen=True)
class EpisodeLease:
    episode_id: str
    run_id: str
    epoch: int
    owner: str
    lease_s: int
    attempt: int = 0


class EpisodeQueue(Protocol):
    async def claim(self, worker_id: str, limit: int, lease_s: int) -> list[EpisodeLease]:
        """Lease up to `limit` runnable episodes; each claim bumps the episode's epoch."""
        ...

    async def heartbeat(self, lease: EpisodeLease) -> bool:
        """Extend the lease. False means it was lost (expired and reclaimed, or finished)."""
        ...

    async def finish(
        self, lease: EpisodeLease, outcome: Outcome, termination: Termination | None = None
    ) -> None:
        """Mark done. Raises StaleLease if the lease is no longer current."""
        ...

    async def release(self, lease: EpisodeLease, *, retry_after_s: int) -> None:
        """Give the episode back; it becomes claimable after `retry_after_s`. No-op if the
        lease is no longer current."""
        ...


@dataclass
class _Row:
    run_id: str
    priority: int
    order: int
    status: str = "queued"
    epoch: int = 0
    owner: str | None = None
    expires_at: float = 0.0
    not_before: float = 0.0
    attempt: int = 0
    outcome: Outcome | None = None
    termination: Termination | None = None


class MemoryEpisodeQueue:
    """Single-process queue. `clock` is injectable so tests can expire leases without sleeping.
    Pass the MemoryJournalStore so claims bump the same epoch the store fences on."""

    def __init__(
        self,
        store: MemoryJournalStore | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._store, self._clock = store, clock
        self._rows: dict[str, _Row] = {}

    def enqueue(
        self, episode_id: str, run_id: str, *, priority: int = 0, not_before_s: float = 0.0
    ) -> None:
        self._rows[episode_id] = _Row(
            run_id, priority, len(self._rows), not_before=self._clock() + not_before_s
        )

    def row(self, episode_id: str) -> _Row:
        return self._rows[episode_id]

    def _current(self, lease: EpisodeLease) -> _Row | None:
        r = self._rows.get(lease.episode_id)
        ok = r and r.status == "leased" and r.epoch == lease.epoch and r.owner == lease.owner
        return r if ok else None

    async def claim(self, worker_id: str, limit: int, lease_s: int) -> list[EpisodeLease]:
        now = self._clock()
        runnable = [
            (eid, r)
            for eid, r in self._rows.items()
            if (r.status == "queued" or (r.status == "leased" and r.expires_at < now))
            and r.not_before <= now
        ]
        runnable.sort(key=lambda p: (-p[1].priority, p[1].order))
        leases = []
        for eid, r in runnable[:limit]:
            r.status, r.owner, r.expires_at, r.epoch = (
                "leased",
                worker_id,
                now + lease_s,
                r.epoch + 1,
            )
            if self._store is not None:
                r.epoch = self._store.bump_epoch(eid)
            leases.append(EpisodeLease(eid, r.run_id, r.epoch, worker_id, lease_s, r.attempt))
        return leases

    async def heartbeat(self, lease: EpisodeLease) -> bool:
        r = self._current(lease)
        if r is None:
            return False
        r.expires_at = self._clock() + lease.lease_s
        return True

    async def finish(
        self, lease: EpisodeLease, outcome: Outcome, termination: Termination | None = None
    ) -> None:
        r = self._current(lease)
        if r is None:
            raise StaleLease(f"{lease.episode_id}: epoch {lease.epoch} is not current")
        r.status, r.owner, r.outcome, r.termination = "done", None, outcome, termination

    async def release(self, lease: EpisodeLease, *, retry_after_s: int) -> None:
        r = self._current(lease)
        if r is None:
            return
        r.status, r.owner = "queued", None
        r.not_before = self._clock() + retry_after_s
