"""Postgres journal store (hard-cores 1.4). `append` takes the episode row lock, so appends
for one episode serialise; the primary keys on events and effects are the second defence."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from gauntlet_core.engine import JournalSnapshot, SeqConflict, StaleLease
from gauntlet_core.schema import EffectRecord, Event
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gauntlet_server.db import Sessionmaker

__all__ = ["PgJournalStore"]

_INSERT_EVENT = text(
    "INSERT INTO events (episode_id, seq, kind, doc) VALUES (:ep, :seq, :kind, CAST(:doc AS jsonb))"
)
_UPSERT_EFFECT = text(
    """
    INSERT INTO effects (episode_id, key, kind, status, request_hash, result, cost)
    VALUES (:ep, :key, :kind, :status, :hash, CAST(:result AS jsonb), CAST(:cost AS jsonb))
    ON CONFLICT (episode_id, key) DO UPDATE SET
      kind = EXCLUDED.kind, status = EXCLUDED.status, request_hash = EXCLUDED.request_hash,
      result = EXCLUDED.result, cost = EXCLUDED.cost
    """
)


def _json(value: Any) -> str | None:
    return None if value is None else json.dumps(value)


class PgJournalStore:
    def __init__(self, sessionmaker: Sessionmaker) -> None:
        self._sm = sessionmaker

    async def load(self, episode_id: str) -> JournalSnapshot:
        """Events, effects and epoch from one consistent snapshot. An unknown episode loads
        as empty at epoch 0 (it cannot be appended to, see `append`)."""
        async with self._sm() as s, s.begin():
            await s.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            epoch = (
                await s.execute(
                    text("SELECT epoch FROM episodes WHERE id = :id"), {"id": episode_id}
                )
            ).scalar()
            ev_rows = (
                await s.execute(
                    text("SELECT doc FROM events WHERE episode_id = :id ORDER BY seq"),
                    {"id": episode_id},
                )
            ).scalars()
            events = [Event.model_validate(d) for d in ev_rows]
            fx_rows = (
                await s.execute(
                    text(
                        "SELECT key, kind, status, request_hash, result, cost "
                        "FROM effects WHERE episode_id = :id"
                    ),
                    {"id": episode_id},
                )
            ).mappings()
            effects = {r["key"]: EffectRecord.model_validate(dict(r)) for r in fx_rows}
        return JournalSnapshot(events, effects, int(epoch or 0))

    async def append(
        self,
        episode_id: str,
        epoch: int,
        *,
        events: Sequence[Event] = (),
        effects: Sequence[EffectRecord] = (),
    ) -> None:
        async with self._sm() as s, s.begin():  # READ COMMITTED: the row lock serialises
            row = (
                await s.execute(
                    text("SELECT epoch, next_seq FROM episodes WHERE id = :id FOR UPDATE"),
                    {"id": episode_id},
                )
            ).first()
            if row is None:
                raise StaleLease(f"{episode_id}: unknown episode")
            cur_epoch, next_seq = row
            if epoch != cur_epoch:
                raise StaleLease(f"{episode_id}: epoch {epoch} != {cur_epoch}")
            if [e.seq for e in events] != list(range(next_seq, next_seq + len(events))):
                raise SeqConflict(f"{episode_id}: events do not continue seq {next_seq}")
            try:
                await self._write(s, episode_id, events, effects)
            except IntegrityError as exc:  # unreachable under the row lock; defence in depth
                raise SeqConflict(f"{episode_id}: {exc.orig}") from exc
            await s.execute(
                text("UPDATE episodes SET next_seq = next_seq + :n WHERE id = :id"),
                {"n": len(events), "id": episode_id},
            )

    async def _write(
        self, s: AsyncSession, ep: str, events: Sequence[Event], effects: Sequence[EffectRecord]
    ) -> None:
        if events:
            await s.execute(
                _INSERT_EVENT,
                [
                    {"ep": ep, "seq": e.seq, "kind": e.kind, "doc": e.model_dump_json()}
                    for e in events
                ],
            )
        added_cost = 0
        for eff in effects:
            prev = (
                await s.execute(
                    text("SELECT status FROM effects WHERE episode_id = :ep AND key = :key"),
                    {"ep": ep, "key": eff.key},
                )
            ).scalar()
            if prev in ("done", "failed") and eff.status == "pending":
                continue  # a finished effect never regresses to pending
            if eff.status == "done" and prev != "done" and eff.cost is not None:
                added_cost += eff.cost.usd_micros
            await s.execute(
                _UPSERT_EFFECT,
                {
                    "ep": ep,
                    "key": eff.key,
                    "kind": eff.kind,
                    "status": eff.status,
                    "hash": eff.request_hash,
                    "result": _json(eff.result),
                    "cost": eff.cost.model_dump_json() if eff.cost else None,
                },
            )
        if added_cost:
            await s.execute(
                text("UPDATE episodes SET cost_usd_micros = cost_usd_micros + :c WHERE id = :id"),
                {"c": added_cost, "id": ep},
            )

    async def abandon_attempt(self, episode_id: str, epoch: int) -> int:
        """Archive the current journal under its attempt number, start a fresh one (CQ-B9).
        Returns the new attempt."""
        async with self._sm() as s, s.begin():
            row = (
                await s.execute(
                    text("SELECT epoch, attempt FROM episodes WHERE id = :id FOR UPDATE"),
                    {"id": episode_id},
                )
            ).first()
            if row is None or row[0] != epoch:
                raise StaleLease(f"{episode_id}: epoch {epoch} is not current")
            attempt = row[1]
            p = {"id": episode_id, "a": attempt}
            await s.execute(
                text(
                    "INSERT INTO events_archive (episode_id, attempt, seq, kind, doc) "
                    "SELECT episode_id, :a, seq, kind, doc FROM events WHERE episode_id = :id"
                ),
                p,
            )
            await s.execute(
                text(
                    "INSERT INTO effects_archive "
                    "(episode_id, attempt, key, kind, status, request_hash, result, cost) "
                    "SELECT episode_id, :a, key, kind, status, request_hash, result, cost "
                    "FROM effects WHERE episode_id = :id"
                ),
                p,
            )
            await s.execute(text("DELETE FROM events WHERE episode_id = :id"), {"id": episode_id})
            await s.execute(text("DELETE FROM effects WHERE episode_id = :id"), {"id": episode_id})
            await s.execute(
                text("UPDATE episodes SET next_seq = 0, attempt = attempt + 1 WHERE id = :id"),
                {"id": episode_id},
            )
            return int(attempt) + 1
