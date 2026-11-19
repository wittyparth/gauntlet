"""Application state shared by the api routes, and the FastAPI dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
from fastapi import Depends, Request
from gauntlet_core.llm import Gateway, GatewayConfig
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import AuthCtx, authenticate
from .config import Settings
from .db import Sessionmaker
from .events import Publisher
from .secrets import SecretStore

__all__ = ["AppState", "auth_ctx", "db_session", "get_state"]


@dataclass
class AppState:
    settings: Settings
    sm: Sessionmaker
    gateway: Gateway
    gateway_config: GatewayConfig
    secrets: SecretStore
    publisher: Publisher
    redis: Any = None  # redis.asyncio.Redis (SSE subscribes through it)
    http: httpx.AsyncClient | None = None
    sse_ping_s: float = 15.0
    closers: list[Callable[[], Awaitable[None]]] = field(default_factory=list)

    async def aclose(self) -> None:
        for close in reversed(self.closers):
            await close()


def get_state(request: Request) -> AppState:
    return request.app.state.gauntlet  # type: ignore[no-any-return]


async def db_session(state: AppState = Depends(get_state)) -> AsyncIterator[AsyncSession]:
    """One session per request. Mutating handlers commit explicitly before returning."""
    async with state.sm() as s:
        yield s


async def auth_ctx(request: Request, session: AsyncSession = Depends(db_session)) -> AuthCtx:
    return await authenticate(session, request.headers.get("authorization"))
