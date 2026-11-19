"""SQLite journal store: the single-file store for the CLI and local runs (CQ-B11).

Same contract as MemoryJournalStore and the Postgres store: atomic append of events and
effects, epoch fencing, dense seq. One connection guarded by a lock; writes use
BEGIN IMMEDIATE so a second process sharing the file serialises on the write lock.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Self

import aiosqlite

from gauntlet_core.schema import EffectRecord, Event

from .errors import SeqConflict, StaleLease
from .store import JournalSnapshot

__all__ = ["SqliteJournalStore"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id TEXT PRIMARY KEY, epoch INTEGER NOT NULL DEFAULT 0, next_seq INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS events (
    episode_id TEXT NOT NULL, seq INTEGER NOT NULL, kind TEXT NOT NULL, doc TEXT NOT NULL,
    PRIMARY KEY (episode_id, seq));
CREATE TABLE IF NOT EXISTS effects (
    episode_id TEXT NOT NULL, key TEXT NOT NULL, status TEXT NOT NULL, doc TEXT NOT NULL,
    PRIMARY KEY (episode_id, key));
"""


class SqliteJournalStore:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn
        self._lock = asyncio.Lock()

    @classmethod
    async def open(cls, path: str = ":memory:") -> Self:
        conn = await aiosqlite.connect(path, isolation_level=None)  # explicit transactions
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.executescript(_SCHEMA)
        return cls(conn)

    async def close(self) -> None:
        await self._conn.close()

    async def bump_epoch(self, episode_id: str) -> int:
        """What claiming the episode does: a new owner, a new fencing token."""
        async with self._lock:
            await self._conn.execute("BEGIN IMMEDIATE")
            try:
                await self._conn.execute(
                    "INSERT OR IGNORE INTO episodes (id) VALUES (?)", (episode_id,)
                )
                await self._conn.execute(
                    "UPDATE episodes SET epoch = epoch + 1 WHERE id = ?", (episode_id,)
                )
                cur = await self._conn.execute(
                    "SELECT epoch FROM episodes WHERE id = ?", (episode_id,)
                )
                row = await cur.fetchone()
                await self._conn.execute("COMMIT")
            except BaseException:
                await self._conn.execute("ROLLBACK")
                raise
            assert row is not None
            return int(row[0])

    async def load(self, episode_id: str) -> JournalSnapshot:
        async with self._lock:
            await self._conn.execute("BEGIN")
            try:
                cur = await self._conn.execute(
                    "SELECT epoch FROM episodes WHERE id = ?", (episode_id,)
                )
                row = await cur.fetchone()
                cur = await self._conn.execute(
                    "SELECT doc FROM events WHERE episode_id = ? ORDER BY seq", (episode_id,)
                )
                events = [Event.model_validate_json(r[0]) for r in await cur.fetchall()]
                cur = await self._conn.execute(
                    "SELECT doc FROM effects WHERE episode_id = ?", (episode_id,)
                )
                effects = [EffectRecord.model_validate_json(r[0]) for r in await cur.fetchall()]
            finally:
                await self._conn.execute("COMMIT")
        return JournalSnapshot(events, {e.key: e for e in effects}, int(row[0]) if row else 0)

    async def append(
        self,
        episode_id: str,
        epoch: int,
        *,
        events: Sequence[Event] = (),
        effects: Sequence[EffectRecord] = (),
    ) -> None:
        async with self._lock:
            await self._conn.execute("BEGIN IMMEDIATE")
            try:
                await self._append(episode_id, epoch, events, effects)
                await self._conn.execute("COMMIT")
            except BaseException:
                await self._conn.execute("ROLLBACK")
                raise

    async def _append(
        self, episode_id: str, epoch: int, events: Sequence[Event], effects: Sequence[EffectRecord]
    ) -> None:
        c = self._conn
        await c.execute("INSERT OR IGNORE INTO episodes (id) VALUES (?)", (episode_id,))
        cur = await c.execute("SELECT epoch, next_seq FROM episodes WHERE id = ?", (episode_id,))
        row = await cur.fetchone()
        assert row is not None
        cur_epoch, next_seq = int(row[0]), int(row[1])
        if epoch != cur_epoch:
            raise StaleLease(f"{episode_id}: epoch {epoch} != {cur_epoch}")
        if [e.seq for e in events] != list(range(next_seq, next_seq + len(events))):
            raise SeqConflict(f"{episode_id}: events do not continue seq {next_seq}")
        await c.executemany(
            "INSERT INTO events (episode_id, seq, kind, doc) VALUES (?, ?, ?, ?)",
            [(episode_id, e.seq, e.kind, e.model_dump_json()) for e in events],
        )
        for eff in effects:
            cur = await c.execute(
                "SELECT status FROM effects WHERE episode_id = ? AND key = ?", (episode_id, eff.key)
            )
            prev = await cur.fetchone()
            if prev and prev[0] in ("done", "failed") and eff.status == "pending":
                continue  # a finished effect never regresses to pending
            await c.execute(
                "INSERT OR REPLACE INTO effects (episode_id, key, status, doc) VALUES (?, ?, ?, ?)",
                (episode_id, eff.key, eff.status, eff.model_dump_json()),
            )
        await c.execute(
            "UPDATE episodes SET next_seq = ? WHERE id = ?", (next_seq + len(events), episode_id)
        )
