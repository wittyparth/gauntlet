"""Rate limiting. The Redis implementation arrives in P1-9; this one is per process."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Protocol

from .config import GatewayConfig


class RateLimiter(Protocol):
    async def acquire(self, provider: str, tokens: int) -> None: ...


class LocalRateLimiter:
    """Two continuously refilled buckets (requests per minute, tokens per minute)."""

    def __init__(
        self,
        rpm: int,
        tpm: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.rpm, self.tpm = rpm, tpm
        self._clock, self._sleep = clock, sleep
        self._req = float(rpm)
        self._tok = float(tpm)
        self._last = clock()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = self._clock()
        dt = max(0.0, now - self._last)
        self._last = now
        self._req = min(float(self.rpm), self._req + dt * self.rpm / 60)
        self._tok = min(float(self.tpm), self._tok + dt * self.tpm / 60)

    async def acquire(self, provider: str, tokens: int) -> None:
        tokens = min(max(tokens, 0), self.tpm)  # an oversize request waits for a full bucket
        async with self._lock:
            while True:
                self._refill()
                wait_r = 0.0 if self._req >= 1 else (1 - self._req) * 60 / self.rpm
                wait_t = 0.0 if self._tok >= tokens else (tokens - self._tok) * 60 / self.tpm
                wait = max(wait_r, wait_t)
                if wait <= 0:
                    self._req -= 1
                    self._tok -= tokens
                    return
                await self._sleep(wait)


class ProviderLimiter:
    """One LocalRateLimiter per configured provider; unconfigured providers are unlimited."""

    def __init__(self, limiters: dict[str, RateLimiter]) -> None:
        self._limiters = limiters

    async def acquire(self, provider: str, tokens: int) -> None:
        lim = self._limiters.get(provider)
        if lim is not None:
            await lim.acquire(provider, tokens)


def build_limiter(config: GatewayConfig) -> RateLimiter:
    return ProviderLimiter(
        {p: LocalRateLimiter(rl.rpm, rl.tpm) for p, rl in config.llm.rate_limits.items()}
    )
