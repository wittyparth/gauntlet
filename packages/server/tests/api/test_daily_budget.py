"""GAUNTLET_DAILY_BUDGET_USD: runs are refused once the rolling 24 h budgets would exceed it."""

from __future__ import annotations

import dataclasses

import pytest
from gauntlet_server.config import Settings

pytestmark = pytest.mark.integration


def test_setting_parses_dollars_to_micros():
    assert (
        Settings.from_env({"GAUNTLET_DAILY_BUDGET_USD": "2.5"}).daily_budget_usd_micros == 2_500_000
    )
    assert Settings.from_env({}).daily_budget_usd_micros == 0


async def test_daily_cap_refuses_then_allows_within_cap(client, state):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    body = {
        "suite_id": seed["suite_id"],
        "agent_version_id": seed["agent_version_id"],
        "budget_usd_micros": 1_000_000,
    }
    state.settings = dataclasses.replace(state.settings, daily_budget_usd_micros=1_500_000)
    ok = await client.post("/v1/runs", json=body)
    assert ok.status_code in (200, 201, 202), ok.text
    over = await client.post("/v1/runs", json=body)
    assert over.status_code == 429
    assert over.json()["error"]["code"] == "daily_budget_exceeded"
    state.settings = dataclasses.replace(state.settings, daily_budget_usd_micros=0)
    assert (await client.post("/v1/runs", json=body)).status_code in (200, 201, 202)
