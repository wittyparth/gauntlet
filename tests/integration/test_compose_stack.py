"""Smoke tests for the compose services (see infra/README.md). Skipped without TEST_DATABASE_URL."""

from __future__ import annotations

import os

import httpx
import pytest
import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration

REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/0")
S3_URL = os.environ.get("TEST_S3_ENDPOINT_URL", "http://localhost:9000")
API_URL = os.environ.get("TEST_API_URL", "http://localhost:8000")


async def test_postgres_has_pgvector():
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    async with engine.connect() as c:
        assert (await c.execute(text("SELECT 1 FROM pg_extension WHERE extname='vector'"))).first()
        assert (await c.execute(text("SELECT version()"))).scalar_one().startswith("PostgreSQL 16")
    await engine.dispose()


async def test_redis_answers_ping():
    client = aioredis.from_url(REDIS_URL)
    assert await client.ping()
    await client.aclose()


async def test_s3_is_live():
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{S3_URL}/healthz")
    assert r.status_code == 200


async def test_api_healthz_when_the_api_service_is_up():
    async with httpx.AsyncClient() as c:
        try:
            r = await c.get(f"{API_URL}/healthz")
        except httpx.ConnectError:
            pytest.skip("api service not running (CI starts only postgres, redis, seaweedfs)")
    assert r.status_code == 200 and r.json()["status"] == "ok"
