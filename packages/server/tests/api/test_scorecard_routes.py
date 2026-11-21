"""Scorecard shape, generated caveats, trend order and the badge link."""

from __future__ import annotations

import pytest
from api_helpers import new_run
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def card(client, seed):
    agent_id = (await client.get("/v1/agents")).json()["items"][0]["id"]
    r = await client.get(f"/v1/agents/{agent_id}/versions/{seed['agent_version_id']}/scorecard")
    assert r.status_code == 200, r.text
    return agent_id, r.json()


async def test_scorecard_shape_trend_and_caveats(client, state, sm):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    second = await new_run(client, state, seed)
    _, c = await card(client, seed)
    assert c["agent_version"]["id"] == seed["agent_version_id"]
    lr = c["latest_run"]
    assert lr["counted"] > 0 and lr["pass_rate"] is not None
    assert c["dimensions"]
    assert {"criterion", "score", "severity", "gating_allowed"} <= set(c["dimensions"][0])
    assert c["cost_per_1000_episodes_usd"] is not None
    stamps = [t["finished_at"] for t in c["trend"]]
    assert stamps == sorted(stamps)  # oldest first
    assert {t["run_id"] for t in c["trend"]} >= {seed["run_id"], second}
    assert c["security"] is None and c["badge"] is None
    assert any("No security run" in x for x in c["caveats"])
    assert any("Fewer than 3 repetitions" in x for x in c["caveats"])
    assert c["generated_at"]


async def test_caveats_follow_run_conditions(client, state, sm):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    async with sm() as s, s.begin():
        await s.execute(text("UPDATE runs SET repetitions = 3, adaptive = true"))
    _, c = await card(client, seed)
    assert not any("Fewer than 3" in x for x in c["caveats"])
    assert any("Adaptive sampling" in x for x in c["caveats"])
    async with sm() as s, s.begin():
        await s.execute(text("UPDATE runs SET status = 'failed'"))
    _, c = await card(client, seed)
    assert c["latest_run"] is None and c["trend"] == []
    assert any("No completed evaluation run" in x for x in c["caveats"])


async def test_badge_link_appears_only_after_a_badge_exists(client):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    agent_id, c = await card(client, seed)
    assert c["badge"] is None
    b = (await client.post(f"/v1/agents/{agent_id}/badge")).json()
    _, c = await card(client, seed)
    assert c["badge"] == {"url": b["url"], "markdown": b["markdown"]}


async def test_scorecard_scoping(client):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    agent_id = (await client.get("/v1/agents")).json()["items"][0]["id"]
    assert (await client.get(f"/v1/agents/{agent_id}/versions/nope/scorecard")).status_code == 404
    other = f"/v1/agents/other/versions/{seed['agent_version_id']}/scorecard"
    assert (await client.get(other)).status_code == 404
