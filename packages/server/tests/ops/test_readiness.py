"""Readiness decision table: tiers, thin samples, thresholds, blockers, baseline."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration

URL = "/v1/agents/agt_demo/versions/agv_demo/readiness"


async def setup(client, sm, passed: int, override: dict | None = None):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    async with sm() as s, s.begin():
        await s.execute(
            text("UPDATE episodes SET outcome = 'failed', finished_at = now() WHERE run_id = :r"),
            {"r": seed["run_id"]},
        )
        await s.execute(
            text(
                "UPDATE episodes SET outcome = 'passed' WHERE id IN "
                "(SELECT id FROM episodes WHERE run_id = :r ORDER BY id LIMIT :n)"
            ),
            {"r": seed["run_id"], "n": passed},
        )
        if override is not None:
            await s.execute(
                text(
                    "INSERT INTO workspace_settings (workspace_id, doc) "
                    "VALUES ('ws_test', CAST(:d AS jsonb)) "
                    "ON CONFLICT (workspace_id) DO UPDATE SET doc = EXCLUDED.doc"
                ),
                {"d": json.dumps({"readiness": {"thresholds": override}})},
            )
    return seed


LENIENT = {
    "high": {
        "success_rate_min": 0.5,
        "pass_hat_k_min": None,
        "attack_success_max": None,
        "min_samples": 5,
    },
    "medium": {
        "success_rate_min": 0.5,
        "pass_hat_k_min": None,
        "attack_success_max": None,
        "min_samples": 5,
    },
    "low": {
        "success_rate_min": 0.5,
        "pass_hat_k_min": None,
        "attack_success_max": None,
        "min_samples": 5,
    },
}


async def test_thin_samples_are_conditional_with_unverified_claims(client, sm):
    await setup(client, sm, 10)
    out = (await client.get(URL)).json()
    assert out["tier"] in ("medium", "high") and out["tier_reasons"]
    assert out["decision"] == "conditional" and out["blockers"] == []
    assert any("samples" in c for c in out["unverified_claims"])
    sr = next(c for c in out["criteria"] if c["id"] == "success_rate")
    assert sr["n"] == 10 and sr["status"] == "unverified" and sr["evidence"]
    assert sr["interval"][0] < 1.0 <= sr["interval"][1] + 1e-9


async def test_go_when_thresholds_are_met_with_enough_samples(client, sm):
    await setup(client, sm, 10, LENIENT)
    out = (await client.get(URL)).json()
    assert out["decision"] == "go" and out["blockers"] == [] and out["unverified_claims"] == []
    assert out["thresholds"]["success_rate_min"] == 0.5


async def test_clear_failure_is_no_go_with_blockers(client, sm):
    await setup(client, sm, 1, LENIENT)  # 1 of 10: the interval ends below 0.5
    out = (await client.get(URL)).json()
    assert out["decision"] == "no_go"
    assert any(b.startswith("Success rate") for b in out["blockers"])


async def test_straddling_the_threshold_is_conditional(client, sm):
    await setup(client, sm, 6, LENIENT)  # 6 of 10: interval contains 0.5
    out = (await client.get(URL)).json()
    sr = next(c for c in out["criteria"] if c["id"] == "success_rate")
    assert sr["status"] == "marginal" and out["decision"] == "conditional"


async def test_open_critical_finding_blocks(client, sm):
    await setup(client, sm, 10, LENIENT)
    async with sm() as s, s.begin():
        await s.execute(
            text(
                "INSERT INTO findings (id, workspace_id, agent_version_id, category, severity, "
                "status, dedup_key, title, doc) VALUES ('fnd_r1', 'ws_test', 'agv_demo', "
                "'data_disclosure', 'critical', 'open', 'k1', 't', '{}'::jsonb)"
            )
        )
    out = (await client.get(URL)).json()
    assert out["decision"] == "no_go" and out["open_findings"]["critical"] == 1
    assert any("critical" in b for b in out["blockers"])


async def test_thresholds_overridable_per_tier_and_baseline_section(client, sm):
    await setup(client, sm, 10, LENIENT)
    out = (await client.get(URL + "?baseline=agv_demo")).json()
    assert out["baseline"]["version_id"] == "agv_demo" and out["baseline"]["regression"] is False
    assert (await client.get(URL + "?baseline=agv_nope")).status_code == 404
    assert (await client.get("/v1/agents/agt_demo/versions/agv_nope/readiness")).status_code == 404
