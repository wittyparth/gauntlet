from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages/server/tests/stores"))

import pytest
import pytest_asyncio
from arena.attempts import Arena
from arena.brain import ScriptedBrain
from arena.settings import ArenaSettings
from gauntlet_server.db import Sessionmaker
from pg_fixtures import migrated_url, sm  # noqa: F401
from sqlalchemy import text


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> Clock:
    return Clock()


class MemRedis:
    """The few Redis calls the arena makes, in memory (a shared Redis would see other suites'
    kill switches)."""

    def __init__(self) -> None:
        self.kv: dict[str, Any] = {}
        self.ttls: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        return await self.incrby(key, 1)

    async def incrby(self, key: str, n: int) -> int:
        self.kv[key] = int(self.kv.get(key, 0)) + n
        return int(self.kv[key])

    async def expire(self, key: str, seconds: int) -> None:
        self.ttls[key] = seconds

    async def ttl(self, key: str) -> int:
        return self.ttls.get(key, -1)

    async def exists(self, key: str) -> int:
        return int(key in self.kv)

    async def get(self, key: str) -> Any:
        return self.kv.get(key)

    async def set(self, key: str, value: Any, ex: int | None = None) -> None:
        self.kv[key] = value
        if ex:
            self.ttls[key] = ex

    async def scan_iter(self, pattern: str, count: int = 10) -> AsyncIterator[str]:
        prefix = pattern.rstrip("*")
        for k in list(self.kv):
            if k.startswith(prefix):
                yield k


@pytest_asyncio.fixture
async def redis() -> MemRedis:
    return MemRedis()


@pytest_asyncio.fixture
async def clean(sm: Sessionmaker) -> Sessionmaker:  # noqa: F811
    async with sm() as s, s.begin():
        await s.execute(
            text("TRUNCATE arena_solves, arena_events, arena_attempts, arena_handles CASCADE")
        )
    return sm


def settings(**kw: Any) -> ArenaSettings:
    base: dict[str, Any] = {
        "enabled": True, "secret": "test-secret", "brain": "scripted",
        "handle_msgs_per_minute": 1000, "ip_per_minute": 1000,
        "attempts_per_handle_per_day": 1000, "open_attempts_per_handle": 50,
    }  # fmt: skip
    base.update(kw)
    return ArenaSettings(**base)


@pytest_asyncio.fixture
async def make_arena(clean: Sessionmaker, redis: Any, clock: Clock) -> AsyncIterator[Any]:
    made: list[Arena] = []

    def make(brain: Any = None, **kw: Any) -> Arena:
        a = Arena(settings(**kw), clean, redis, brain or ScriptedBrain(), clock=clock)
        made.append(a)
        return a

    yield make
    for a in made:
        await a.shutdown()
