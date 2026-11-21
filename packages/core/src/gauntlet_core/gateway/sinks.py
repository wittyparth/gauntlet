"""Where decision records go (P4-2). Sinks never raise into the agent path: `write` only
queues; failures are counted by the guard or the sink."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

import httpx

from .decision import DecisionRecord

__all__ = ["DecisionSink", "HttpSink", "JsonlSink", "MemorySink"]

log = logging.getLogger("gauntlet.gateway")


class DecisionSink(Protocol):
    async def write(self, record: DecisionRecord) -> None: ...


class MemorySink:
    def __init__(self) -> None:
        self.records: list[DecisionRecord] = []

    async def write(self, record: DecisionRecord) -> None:
        self.records.append(record)


class JsonlSink:
    """Appends one JSON object per line."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = asyncio.Lock()

    async def write(self, record: DecisionRecord) -> None:
        line = record.model_dump_json() + "\n"
        async with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line)


class HttpSink:
    """Batches records to `POST /v1/gateway/decisions`.

    A bounded in-memory queue (drop oldest, counted in `dropped`); batches of up to
    `batch_size`, sent every `flush_interval_s` or as soon as `flush_threshold` are queued;
    exponential backoff (capped at `max_backoff_s`) on 5xx and connection errors; `aclose()`
    flushes. `write` never blocks on the network.
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        *,
        flush_interval_s: float = 2.0,
        max_queue: int = 10_000,
        batch_size: int = 500,
        flush_threshold: int = 200,
        max_backoff_s: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.flush_interval_s = flush_interval_s
        self.max_queue = max_queue
        self.batch_size = batch_size
        self.flush_threshold = flush_threshold
        self.max_backoff_s = max_backoff_s
        self._sleep = sleep
        self._client = httpx.AsyncClient(
            base_url=api_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
            timeout=10.0,
        )
        self._queue: deque[DecisionRecord] = deque()
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._closed = False
        self.dropped = 0
        self.sent = 0
        self.failures = 0
        self.backoffs: list[float] = []  # the delays used, for tests and metrics

    @property
    def queued(self) -> int:
        return len(self._queue)

    async def write(self, record: DecisionRecord) -> None:
        if self._closed:
            return
        if len(self._queue) >= self.max_queue:
            self._queue.popleft()
            self.dropped += 1
        self._queue.append(record)
        if self._task is None:
            self._task = asyncio.create_task(self._run())
        if len(self._queue) >= self.flush_threshold:
            self._wake.set()

    async def _send_one(self) -> bool:
        """Send up to one batch. True when it was accepted (or nothing was queued)."""
        if not self._queue:
            return True
        batch = [self._queue[i] for i in range(min(self.batch_size, len(self._queue)))]
        try:
            r = await self._client.post(
                "/v1/gateway/decisions",
                json={"records": [rec.model_dump(mode="json") for rec in batch]},
            )
        except httpx.TransportError:
            return False
        if r.status_code >= 500:
            return False
        if r.status_code >= 400:  # a rejected batch will never succeed: drop it, count it
            log.warning("gateway sink: server rejected a batch (%s); dropping it", r.status_code)
            self.dropped += len(batch)
        else:
            self.sent += len(batch)
        for _ in batch:
            self._queue.popleft()
        return True

    async def flush(self) -> bool:
        """Send everything queued. False when a batch failed (it stays queued)."""
        while self._queue:
            if not await self._send_one():
                self.failures += 1
                return False
        return True

    async def _run(self) -> None:
        delay = 0.0
        while not self._closed:
            if delay:
                self.backoffs.append(delay)
                await self._sleep(delay)
            else:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._wake.wait(), self.flush_interval_s)
            self._wake.clear()
            ok = await self.flush()
            delay = 0.0 if ok else min(self.max_backoff_s, (delay * 2) or 1.0)

    async def aclose(self) -> None:
        self._closed = True
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        await self.flush()
        await self._client.aclose()
