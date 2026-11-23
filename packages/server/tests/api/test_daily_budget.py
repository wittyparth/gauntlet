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


async def test_finished_runs_count_real_spend_not_their_budget(client, state, sm):
    from sqlalchemy import text

    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    body = {
        "suite_id": seed["suite_id"],
        "agent_version_id": seed["agent_version_id"],
        "budget_usd_micros": 1_000_000,
    }
    state.settings = dataclasses.replace(state.settings, daily_budget_usd_micros=1_500_000)
    first = (await client.post("/v1/runs", json=body)).json()
    assert (await client.post("/v1/runs", json=body)).status_code == 429  # 1.0 + 1.0 > 1.5
    async with sm() as s, s.begin():  # the first run finishes having spent $0.01
        await s.execute(
            text(
                "UPDATE runs SET status = 'done', reserved_usd_micros = 0, "
                "spent_usd_micros = 10000 WHERE id = :id"
            ),
            {"id": first["id"]},
        )
    assert (await client.post("/v1/runs", json=body)).status_code in (200, 201, 202)
