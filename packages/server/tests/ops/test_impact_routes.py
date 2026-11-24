"""POST /v1/impact: selection by change class, reasons, full-run flag, typed output."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def add_version(sm, vid: str, overrides: dict, world_id: str | None = None) -> str:
    """A copy of the demo version's config with `overrides` applied."""
    async with sm() as s, s.begin():
        await s.execute(
            text(
                "INSERT INTO agent_versions (id, workspace_id, agent_id, label, config, world_id) "
                "SELECT :i, workspace_id, agent_id, :i, config || CAST(:o AS jsonb), "
                "coalesce(:w, world_id) "
                "FROM agent_versions WHERE id = 'agv_demo'"
            ),
            {"i": vid, "o": json.dumps(overrides), "w": world_id},
        )
    return vid


async def seed(client):
    return (await client.post("/v1/dev/seed", json={"reset": False})).json()


async def referencing(sm, tool: str) -> set[str]:
    """Scenarios whose checks name the tool, or whose past episodes called it."""
    async with sm() as s:
        rows = await s.execute(
            text(
                "SELECT id FROM scenarios WHERE status = 'approved' AND "
                "((doc->'success')::text LIKE :p OR (doc->'forbidden')::text LIKE :p) "
                "UNION SELECT e.scenario_id FROM events ev JOIN episodes e ON e.id = ev.episode_id "
                "WHERE ev.kind = 'tool_call' AND ev.doc #>> '{payload,tool}' = :t"
            ),
            {"p": f'%"tool": "{tool}"%', "t": tool},
        )
        return set(rows.scalars())


async def test_tool_change_selects_exactly_the_referencing_scenarios_plus_pinned(client, sm):
    await seed(client)
    async with sm() as s, s.begin():
        await s.execute(text("UPDATE scenarios SET source = 'pinned' WHERE id = 'scn_ecom_15'"))
    v2 = await add_version(sm, "agv_t2", {"tools": ["issue_refund"]})
    r = await client.post("/v1/impact", json={"from_version": "agv_demo", "to_version": v2})
    assert r.status_code == 200, r.text
    out = r.json()
    want = (await referencing(sm, "issue_refund")) | {"scn_ecom_15"}
    assert set(out["scenario_ids"]) == want and not out["full_run"]
    assert out["change"]["tools"] == ["issue_refund"]
    assert out["reasons"]["scn_ecom_15"] == ["pinned regression"]
    assert all(out["reasons"][i] for i in out["scenario_ids"])
    assert out["suggested_suite"]["scenario_ids"] == out["scenario_ids"]
    assert out["total_scenarios"] >= len(want)


async def test_model_change_samples_by_risk_and_includes_pinned(client, sm):
    await seed(client)
    async with sm() as s, s.begin():
        await s.execute(text("UPDATE scenarios SET source = 'pinned' WHERE id = 'scn_ecom_20'"))
    v2 = await add_version(sm, "agv_t3", {"model": "other-model"})
    out = (
        await client.post("/v1/impact", json={"from_version": "agv_demo", "to_version": v2})
    ).json()
    assert out["change"]["model"] and not out["full_run"]
    assert "scn_ecom_20" in out["scenario_ids"]
    assert 0 < len(out["scenario_ids"]) < out["total_scenarios"]
    assert any("risk sample" in why for rs in out["reasons"].values() for why in rs)


async def test_unknown_change_is_a_full_run(client, sm):
    await seed(client)
    v2 = await add_version(sm, "agv_t4", {"endpoint": "http://elsewhere.test"})
    out = (
        await client.post("/v1/impact", json={"from_version": "agv_demo", "to_version": v2})
    ).json()
    assert out["full_run"] and len(out["scenario_ids"]) == out["total_scenarios"]


async def test_identical_versions_select_nothing_and_errors(client, sm):
    await seed(client)
    same = await add_version(sm, "agv_t5", {})
    out = (
        await client.post("/v1/impact", json={"from_version": "agv_demo", "to_version": same})
    ).json()
    assert out["scenario_ids"] == [] and not out["full_run"]
    miss = await client.post("/v1/impact", json={"from_version": "agv_demo", "to_version": "nope"})
    assert miss.status_code == 404
    half = await client.post(
        "/v1/impact", json={"from_version": "agv_demo", "to_version": same, "policy_from": "p"}
    )
    assert half.status_code == 422


async def test_nested_target_prompt_change_is_a_prompt_change_not_unknown(client, sm):
    """Stored configs nest model, prompt and tools under `target`; that must be classified."""
    await seed(client)
    async with sm() as s, s.begin():
        await s.execute(
            text(
                "INSERT INTO agent_versions (id, workspace_id, agent_id, label, config, world_id) "
                "SELECT 'agv_t6', workspace_id, agent_id, 'agv_t6', "
                "jsonb_set(config, '{target,system_prompt}', '\"a different prompt\"'), world_id "
                "FROM agent_versions WHERE id = 'agv_demo'"
            )
        )
    out = (
        await client.post("/v1/impact", json={"from_version": "agv_demo", "to_version": "agv_t6"})
    ).json()
    assert out["change"]["prompt"] and not out["full_run"]
    assert 0 < len(out["scenario_ids"]) < out["total_scenarios"]
