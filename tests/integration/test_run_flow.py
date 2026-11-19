"""Seed through the running compose api and read the report. Skipped when the api is down."""

from __future__ import annotations

import os

import httpx
import pytest

pytestmark = pytest.mark.integration

API_URL = os.environ.get("TEST_API_URL", "http://localhost:8000")
KEY = os.environ.get("TEST_API_KEY", "gk_dev_local_only")


async def test_dev_seed_then_report_over_http():
    async with httpx.AsyncClient(base_url=API_URL, headers={"Authorization": f"Bearer {KEY}"}) as c:
        try:
            r = await c.post("/v1/dev/seed", json={"reset": False}, timeout=60)
        except httpx.ConnectError:
            pytest.skip("api service not running")
        if r.status_code in (401, 404):
            pytest.skip("api is not in dev mode or the dev key is not seeded")
        assert r.status_code == 200, r.text
        seed = r.json()
        report = (await c.get(f"/v1/runs/{seed['run_id']}/report")).json()
        assert report["counted"] == 6
