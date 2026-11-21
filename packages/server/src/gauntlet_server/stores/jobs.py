"""Postgres job queue (P3-5): the episode queue's lease pattern for generic background jobs.
Every timestamp is the database clock. At-least-once: an expired lease is claimable again,
up to `MAX_ATTEMPTS` claims, after which the job is `failed`."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from gauntlet_core.ids import new_id
from sqlalchemy import text

from gauntlet_server.db import Sessionmaker

__all__ = ["MAX_ATTEMPTS", "JobLease", "PgJobQueue"]

MAX_ATTEMPTS = 3

_CLAIM = text(
    """
    WITH c AS MATERIALIZED (
        SELECT id FROM jobs
        WHERE ((status = 'queued') OR (status = 'running' AND lease_expires_at < now()))
          AND not_before <= now() AND attempts < :max_attempts
        ORDER BY created_at ASC
        FOR UPDATE SKIP LOCKED
        LIMIT :n)
    UPDATE jobs SET status = 'running', lease_owner = :worker, attempts = attempts + 1,
        lease_expires_at = now() + :lease_s * interval '1 second'
    FROM c WHERE jobs.id = c.id
    RETURNING jobs.id, jobs.workspace_id, jobs.kind, jobs.payload, jobs.attempts, jobs.created_at
    """
)
# a job whose lease expired with no attempts left can never be claimed again: fail it
_REAP = text(
    "UPDATE jobs SET status = 'failed', error = coalesce(error, 'lease expired after '"
    " || attempts || ' attempts'), finished_at = now(), lease_owner = NULL "
    "WHERE status = 'running' AND lease_expires_at < now() AND attempts >= :max_attempts"
)
_HOLDS = "id = :id AND status = 'running' AND lease_owner = :owner"


@dataclass(frozen=True)
class JobLease:
    id: str
    workspace_id: str
    kind: str
    payload: dict[str, Any]
    attempts: int
    owner: str
    lease_s: int


class PgJobQueue:
    def __init__(self, sessionmaker: Sessionmaker) -> None:
        self._sm = sessionmaker

    async def enqueue(
        self, workspace_id: str, kind: str, payload: dict[str, Any], *, session: Any = None
    ) -> str:
        """Inside `session`'s transaction when given (the caller commits), else on its own."""
        job_id = new_id("job")
        stmt = text(
            "INSERT INTO jobs (id, workspace_id, kind, payload) "
            "VALUES (:id, :ws, :kind, CAST(:p AS jsonb))"
        )
        params = {"id": job_id, "ws": workspace_id, "kind": kind, "p": json.dumps(payload)}
        if session is not None:
            await session.execute(stmt, params)
        else:
            async with self._sm() as s, s.begin():
                await s.execute(stmt, params)
        return job_id

    async def claim(self, worker_id: str, limit: int, lease_s: int) -> list[JobLease]:
        if limit <= 0:
            return []
        async with self._sm() as s, s.begin():
            await s.execute(_REAP, {"max_attempts": MAX_ATTEMPTS})
            rows = (
                await s.execute(
                    _CLAIM,
                    {
                        "worker": worker_id,
                        "lease_s": lease_s,
                        "n": limit,
                        "max_attempts": MAX_ATTEMPTS,
                    },
                )
            ).all()
        rows = sorted(rows, key=lambda r: r.created_at)
        return [
            JobLease(r.id, r.workspace_id, r.kind, r.payload, r.attempts, worker_id, lease_s)
            for r in rows
        ]

    async def heartbeat(self, lease: JobLease) -> bool:
        async with self._sm() as s, s.begin():
            res = await s.execute(
                text(
                    "UPDATE jobs SET lease_expires_at = now() + :lease_s * interval '1 second' "
                    f"WHERE {_HOLDS}"
                ),
                {"id": lease.id, "owner": lease.owner, "lease_s": lease.lease_s},
            )
            return res.rowcount == 1  # type: ignore[attr-defined]

    async def complete(self, lease: JobLease, result: dict[str, Any]) -> bool:
        async with self._sm() as s, s.begin():
            res = await s.execute(
                text(
                    "UPDATE jobs SET status = 'done', result = CAST(:r AS jsonb), "
                    "finished_at = now(), lease_owner = NULL, lease_expires_at = NULL "
                    f"WHERE {_HOLDS}"
                ),
                {"id": lease.id, "owner": lease.owner, "r": json.dumps(result)},
            )
            return res.rowcount == 1  # type: ignore[attr-defined]

    async def fail(self, lease: JobLease, error: str) -> bool:
        """Retry (back to `queued`) while attempts remain, else `failed`."""
        async with self._sm() as s, s.begin():
            res = await s.execute(
                text(
                    "UPDATE jobs SET error = :e, lease_owner = NULL, lease_expires_at = NULL, "
                    "status = CASE WHEN attempts >= :m THEN 'failed' ELSE 'queued' END, "
                    "finished_at = CASE WHEN attempts >= :m THEN now() END "
                    f"WHERE {_HOLDS}"
                ),
                {"id": lease.id, "owner": lease.owner, "e": error[:2000], "m": MAX_ATTEMPTS},
            )
            return res.rowcount == 1  # type: ignore[attr-defined]
