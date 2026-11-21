"""Remote traffic limits (P2-4): a per-host counting semaphore and a minimum gap between
requests, both in Redis so every worker shares them. Wrapped around the worker's httpx transport
for non-local hosts only."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Collection
from contextlib import asynccontextmanager
from typing import Any

import httpx

__all__ = ["HostLimiter", "LimitedTransport"]


class HostLimiter:
    def __init__(
        self,
        redis: Any,
        *,
        max_concurrent: int = 2,
        min_gap_s: float = 0.25,
        ttl_s: int = 120,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.redis, self.max, self.gap, self.ttl, self._sleep = (
            redis,
            max_concurrent,
            min_gap_s,
            ttl_s,
            sleep,
        )

    @asynccontextmanager
    async def slot(self, host: str) -> AsyncIterator[None]:
        key = f"gauntlet:hostsem:{host}"
        while True:
            n = await self.redis.incr(key)
            await self.redis.expire(key, self.ttl)
            if n <= self.max:
                break
            await self.redis.decr(key)
            await self._sleep(0.05)
        try:
            last = f"gauntlet:hostlast:{host}"
            while not await self.redis.set(last, "1", nx=True, px=max(1, int(self.gap * 1000))):
                await self._sleep(0.02)
            yield
        finally:
            await self.redis.decr(key)


class LimitedTransport(httpx.AsyncBaseTransport):
    def __init__(
        self, inner: httpx.AsyncBaseTransport, limiter: HostLimiter, local_hosts: Collection[str]
    ) -> None:
        self._inner, self._limiter = inner, limiter
        self._local = {h.lower() for h in local_hosts} | {"localhost", "127.0.0.1", "::1"}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host.lower()
        if host in self._local:
            return await self._inner.handle_async_request(request)
        async with self._limiter.slot(host):
            resp = await self._inner.handle_async_request(request)
            await resp.aread()
            return resp

    async def aclose(self) -> None:
        await self._inner.aclose()
