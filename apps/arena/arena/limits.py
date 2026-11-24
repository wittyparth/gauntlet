"""Anti-abuse limits. Counters live in Redis under hashed keys: no address, handle or text is
kept beyond a short window."""

from __future__ import annotations

import hashlib
from typing import Any

from .settings import ArenaSettings

__all__ = ["ArenaClosed", "Limiter", "RateLimited", "closed_reason", "hash_key"]

KILL_PREFIX = "gauntlet:kill:"  # the platform kill switch (P2-4): any engaged scope closes us
CLOSED_KEY = "arena:closed"


class RateLimited(Exception):
    def __init__(self, what: str, retry_after_s: int) -> None:
        super().__init__(what)
        self.what, self.retry_after_s = what, retry_after_s


class ArenaClosed(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def hash_key(secret: str, value: str) -> str:
    return hashlib.sha256(f"{secret}:{value}".encode()).hexdigest()[:20]


async def closed_reason(redis: Any, settings: ArenaSettings) -> str | None:
    """Why the arena is closed right now, or None when it is open."""
    if not settings.enabled:
        return "disabled"
    if await redis.exists(CLOSED_KEY):
        return "closed"
    async for _ in redis.scan_iter(f"{KILL_PREFIX}*", count=50):
        return "killswitch"
    return None


class Limiter:
    def __init__(self, redis: Any, settings: ArenaSettings) -> None:
        self.redis, self.s = redis, settings

    async def _hit(self, key: str, limit: int, window_s: int, what: str) -> None:
        n = await self.redis.incr(key)
        if n == 1:
            await self.redis.expire(key, window_s)
        if n > limit:
            ttl = await self.redis.ttl(key)
            raise RateLimited(what, max(1, int(ttl)))

    async def ip(self, ip: str) -> None:
        key = f"arena:rl:ip:{hash_key(self.s.secret, ip)}"
        await self._hit(key, self.s.ip_per_minute, 60, "ip")

    async def message(self, handle: str) -> None:
        key = f"arena:rl:msg:{hash_key(self.s.secret, handle)}"
        await self._hit(key, self.s.handle_msgs_per_minute, 60, "handle")

    async def attempt(self, handle: str, day: str) -> None:
        key = f"arena:rl:att:{day}:{hash_key(self.s.secret, handle)}"
        await self._hit(key, self.s.attempts_per_handle_per_day, 86400, "attempts_per_day")
