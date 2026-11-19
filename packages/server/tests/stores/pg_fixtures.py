"""Shared Postgres fixtures, re-exported by tests/conftest.py."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from gauntlet_core.engine import SqliteJournalStore
from gauntlet_server.db import Sessionmaker, make_engine, make_sessionmaker
from harness import Harness, MemoryHarness, PgHarness, SqliteHarness
from pg_helpers import database_url, migrate_sync, reset


@pytest.fixture(scope="session")
def migrated_url() -> str:
    """The test database at alembic head (only requested by integration tests)."""
    url = database_url()
    migrate_sync(url, "upgrade", "head")
    return url


@pytest_asyncio.fixture
async def sm(migrated_url: str) -> AsyncIterator[Sessionmaker]:
    engine = make_engine(migrated_url)
    maker = make_sessionmaker(engine)
    await reset(maker)
    yield maker
    await engine.dispose()


@pytest_asyncio.fixture(
    params=["memory", "sqlite", pytest.param("postgres", marks=pytest.mark.integration)]
)
async def backend(request: pytest.FixtureRequest) -> AsyncIterator[Harness]:
    if request.param == "memory":
        yield MemoryHarness()
    elif request.param == "sqlite":
        store = await SqliteJournalStore.open()
        yield SqliteHarness(store)
        await store.close()
    else:
        engine = make_engine(request.getfixturevalue("migrated_url"))
        maker = make_sessionmaker(engine)
        await reset(maker)
        yield PgHarness(maker)
        await engine.dispose()
