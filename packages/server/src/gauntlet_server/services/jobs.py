"""Background jobs (P3-5): handler registry and the runner the worker's job loop uses.

Handlers are `async (JobContext) -> Json`, at-least-once, therefore idempotent (a calibration
keys its result on its own row id). Kinds in this phase: `calibrate`, `cluster`."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from ..deps import AppState
from ..stores.jobs import JobLease, PgJobQueue

__all__ = ["JOB_HANDLERS", "JobContext", "JobHandler", "handler", "run_job"]

log = logging.getLogger("gauntlet.jobs")


@dataclass(frozen=True)
class JobContext:
    state: AppState
    job_id: str
    workspace_id: str
    kind: str
    payload: dict[str, Any]
    attempts: int


JobHandler = Callable[[JobContext], Awaitable[dict[str, Any]]]
JOB_HANDLERS: dict[str, JobHandler] = {}


def handler(kind: str) -> Callable[[JobHandler], JobHandler]:
    def deco(fn: JobHandler) -> JobHandler:
        JOB_HANDLERS[kind] = fn
        return fn

    return deco


async def _beat(queue: PgJobQueue, lease: JobLease, task: asyncio.Task[Any]) -> None:
    while True:
        await asyncio.sleep(lease.lease_s / 3)
        try:
            if not await queue.heartbeat(lease):
                task.cancel()  # lease lost: someone else owns the job now
                return
        except Exception:
            log.warning("job heartbeat error for %s", lease.id, exc_info=True)


async def run_job(state: AppState, queue: PgJobQueue, lease: JobLease) -> None:
    """Run one claimed job under a heartbeat and record the result or the error."""
    fn = JOB_HANDLERS.get(lease.kind)
    if fn is None:
        await queue.fail(lease, f"unknown job kind {lease.kind!r}")
        return
    me = asyncio.current_task()
    assert me is not None
    beat = asyncio.create_task(_beat(queue, lease, me))
    try:
        ctx = JobContext(
            state, lease.id, lease.workspace_id, lease.kind, lease.payload, lease.attempts
        )
        result = await fn(ctx)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.exception("job %s (%s) failed", lease.id, lease.kind)
        await queue.fail(lease, f"{type(e).__name__}: {e}")
    else:
        await queue.complete(lease, result)
    finally:
        beat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await beat
