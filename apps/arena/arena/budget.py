"""The arena's daily dollar budget. When the day's spend reaches the cap the arena closes by
itself until the next UTC day."""

from __future__ import annotations

from typing import Any

from .limits import CLOSED_KEY

__all__ = ["DailyBudget"]


class DailyBudget:
    def __init__(self, redis: Any, cap_usd_micros: int) -> None:
        self.redis, self.cap = redis, cap_usd_micros

    @staticmethod
    def _key(day: str) -> str:
        return f"arena:budget:{day}"

    async def spent(self, day: str) -> int:
        return int(await self.redis.get(self._key(day)) or 0)

    async def add(self, day: str, usd_micros: int, seconds_left: int) -> bool:
        """Record spend. Returns True (and closes the arena) when the cap is reached."""
        if usd_micros <= 0:
            return False
        total = int(await self.redis.incrby(self._key(day), usd_micros))
        await self.redis.expire(self._key(day), 2 * 86400)
        if self.cap > 0 and total >= self.cap:
            await self.redis.set(CLOSED_KEY, "budget", ex=max(60, seconds_left))
            return True
        return False
