from __future__ import annotations

import os
from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from gauntlet_core.llm import GatewayConfig, ScriptedLLM
from gauntlet_server.app import create_app
from gauntlet_server.auth import hash_key
from gauntlet_server.config import Settings
from gauntlet_server.deps import AppState
from gauntlet_server.events import RedisPublisher
from gauntlet_server.secrets import SecretStore
from gauntlet_server.services.seed import script
from pg_helpers import database_url
from redis import asyncio as aioredis
from sqlalchemy import text

KEY = "gk_test_key"


@pytest_asyncio.fixture
async def state(sm) -> AsyncIterator[AppState]:
    url = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/0")
    redis = aioredis.from_url(url)
    settings = Settings(
        env="dev",
        database_url=database_url(),
        redis_url=url,
        public_api_url="http://api.test",
        lease_s=2,
        poll_interval_s=0.05,
    )
    async with sm() as s, s.begin():
        await s.execute(
            text(
                "INSERT INTO api_keys (id, workspace_id, hash, prefix, name, scopes) "
                "VALUES ('key_t', 'ws_test', :h, 'gk_test_', 't', '[\"admin\"]')"
            ),
            {"h": hash_key(KEY)},
        )
    st = AppState(
        settings=settings,
        sm=sm,
        gateway=ScriptedLLM(script()),
        gateway_config=GatewayConfig(),
        secrets=SecretStore(sm, settings.fernet_key()),
        publisher=RedisPublisher(redis),
        redis=redis,
        sse_ping_s=0.3,
    )
    yield st
    await redis.aclose()


@pytest_asyncio.fixture
async def client(state: AppState) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(state)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://api.test", headers={"Authorization": f"Bearer {KEY}"}
    ) as c:
        yield c
