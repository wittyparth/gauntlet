"""Public benchmarks route: typed, unauthenticated, no workspace data, empty when no files."""

from __future__ import annotations

import dataclasses
import json

import httpx
import pytest
from gauntlet_server.app import create_app

pytestmark = pytest.mark.integration

RESULT = {
    "name": "demo", "version": 1, "seed": 0, "platform_version": "0.1.0",
    "started_at": "2026-01-01T00:00:00Z", "smoke": False, "metrics": {"a": 0.5},
    "intervals": {"a": [0.4, 0.6]}, "n": 10, "limitations": ["l"], "notes": "",
}  # fmt: skip
URL = "/v1/meta/benchmarks"


@pytest.fixture
async def anon(state):
    transport = httpx.ASGITransport(app=create_app(state))
    async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as c:
        yield c


async def test_empty_directory_gives_an_empty_list(anon, state, tmp_path):
    state.settings = dataclasses.replace(state.settings, benchmarks_dir=str(tmp_path / "none"))
    r = await anon.get(URL)
    assert r.status_code == 200 and r.json() == {"studies": []}
    assert "max-age" in r.headers["cache-control"]


async def test_serves_files_without_credentials_and_skips_invalid(anon, state, tmp_path):
    (tmp_path / "demo.json").write_text(json.dumps(RESULT))
    (tmp_path / "bad.json").write_text("{not json")
    state.settings = dataclasses.replace(state.settings, benchmarks_dir=str(tmp_path))
    r = await anon.get(URL)
    assert r.status_code == 200
    studies = r.json()["studies"]
    assert [s["name"] for s in studies] == ["demo"]
    assert studies[0]["intervals"]["a"] == [0.4, 0.6]
    assert set(studies[0]) <= set(RESULT)  # nothing beyond the result schema


async def test_cache_refreshes_when_a_file_changes(anon, state, tmp_path):
    state.settings = dataclasses.replace(state.settings, benchmarks_dir=str(tmp_path))
    (tmp_path / "a.json").write_text(json.dumps(RESULT))
    assert len((await anon.get(URL)).json()["studies"]) == 1
    (tmp_path / "b.json").write_text(json.dumps({**RESULT, "name": "other"}))
    assert len((await anon.get(URL)).json()["studies"]) == 2
