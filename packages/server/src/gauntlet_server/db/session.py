"""Engine and sessionmaker construction."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

__all__ = ["Sessionmaker", "make_engine", "make_sessionmaker"]

Sessionmaker = async_sessionmaker[AsyncSession]


def make_engine(url: str, **kw: object) -> AsyncEngine:
    opts: dict[str, object] = {"pool_size": 10, "max_overflow": 10, "pool_pre_ping": True}
    opts.update(kw)
    return create_async_engine(url, **opts)


def make_sessionmaker(engine: AsyncEngine) -> Sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)
