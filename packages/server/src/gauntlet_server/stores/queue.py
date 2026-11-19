"""Postgres episode queue (hard-cores 1.4). Every timestamp is the database clock (`now()`);
the Python process clock is never consulted, so worker clock skew cannot steal or pin leases."""

from __future__ import annotations

from gauntlet_core.engine import EpisodeLease, StaleLease
from gauntlet_core.schema import Outcome, Termination
from sqlalchemy import text

from gauntlet_server.db import Sessionmaker

__all__ = ["PgEpisodeQueue"]

_CLAIM = text(
    """
    WITH c AS MATERIALIZED (
        SELECT id FROM episodes
        WHERE (status = 'queued' OR (status = 'leased' AND lease_expires_at < now()))
          AND not_before <= now()
          AND run_id IN (SELECT id FROM runs WHERE status IN ('queued', 'running'))
        ORDER BY priority DESC, created_at ASC
        FOR UPDATE SKIP LOCKED
        LIMIT :n)
    UPDATE episodes SET status = 'leased', lease_owner = :worker, epoch = epoch + 1,
        lease_expires_at = now() + :lease_s * interval '1 second',
        started_at = coalesce(started_at, now())
    FROM c WHERE episodes.id = c.id
    RETURNING episodes.id, episodes.run_id, episodes.epoch, episodes.attempt,
        episodes.priority, episodes.created_at
    """
)
_HOLDS = "id = :id AND epoch = :epoch AND status = 'leased' AND lease_owner = :owner"


class PgEpisodeQueue:
    def __init__(self, sessionmaker: Sessionmaker) -> None:
        self._sm = sessionmaker

    async def claim(self, worker_id: str, limit: int, lease_s: int) -> list[EpisodeLease]:
        if limit <= 0:
            return []
        async with self._sm() as s, s.begin():
            rows = (
                await s.execute(_CLAIM, {"worker": worker_id, "lease_s": lease_s, "n": limit})
            ).all()
            run_ids = sorted({r.run_id for r in rows})
            if run_ids:
                await s.execute(
                    text(
                        "UPDATE runs SET status = 'running' "
                        "WHERE id = ANY(:ids) AND status = 'queued'"
                    ),
                    {"ids": run_ids},
                )
        rows = sorted(rows, key=lambda r: (-r.priority, r.created_at))  # RETURNING is unordered
        return [EpisodeLease(r.id, r.run_id, r.epoch, worker_id, lease_s, r.attempt) for r in rows]

    def _params(self, lease: EpisodeLease) -> dict[str, object]:
        return {"id": lease.episode_id, "epoch": lease.epoch, "owner": lease.owner}

    async def heartbeat(self, lease: EpisodeLease) -> bool:
        async with self._sm() as s, s.begin():
            res = await s.execute(
                text(
                    "UPDATE episodes SET lease_expires_at = now() + :lease_s * interval '1 second' "
                    f"WHERE {_HOLDS}"
                ),
                {**self._params(lease), "lease_s": lease.lease_s},
            )
            return res.rowcount == 1  # type: ignore[attr-defined]

    async def finish(
        self, lease: EpisodeLease, outcome: Outcome, termination: Termination | None = None
    ) -> None:
        async with self._sm() as s, s.begin():
            res = await s.execute(
                text(
                    "UPDATE episodes SET status = 'done', outcome = :outcome, "
                    "termination = :termination, finished_at = now(), lease_owner = NULL, "
                    f"lease_expires_at = NULL WHERE {_HOLDS}"
                ),
                {**self._params(lease), "outcome": outcome, "termination": termination},
            )
            if res.rowcount != 1:  # type: ignore[attr-defined]
                raise StaleLease(f"{lease.episode_id}: epoch {lease.epoch} is not current")

    async def release(self, lease: EpisodeLease, *, retry_after_s: int) -> None:
        async with self._sm() as s, s.begin():
            await s.execute(
                text(
                    "UPDATE episodes SET status = 'queued', lease_owner = NULL, "
                    "lease_expires_at = NULL, "
                    f"not_before = now() + :retry * interval '1 second' WHERE {_HOLDS}"
                ),
                {**self._params(lease), "retry": retry_after_s},
            )
