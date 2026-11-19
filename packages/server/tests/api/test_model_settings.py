"""Catalog, per-workspace model settings, and the resolved models on a run."""

from __future__ import annotations

import pytest
from gauntlet_core.llm import GatewayConfig, LiteLLMGateway, ScriptedLLM
from gauntlet_server.models_gateway import gateway_for_roles

QWEN38 = "openrouter/qwen/qwen3.8-flash"
ROLES = {"simulator", "judge_small", "judge_strong", "attacker", "generator"}


@pytest.mark.integration
async def test_catalog_route(client):
    r = await client.get("/v1/models/catalog")
    assert r.status_code == 200
    models = r.json()["models"]
    ids = [m["id"] for m in models]
    assert "openrouter/qwen/qwen3.7-flash" in ids
    assert not any("/openai/" in i or "/anthropic/" in i for i in ids)
    m = models[0]
    for key in ("name", "input_usd_per_mtok", "good_for", "description", "recommended_roles"):
        assert key in m
    assert "supports_reasoning_off" in m and "reasoning_default" in m


@pytest.mark.integration
async def test_defaults_then_put_get_reset(client):
    r = await client.get("/v1/settings/models")
    assert r.status_code == 200
    body = r.json()
    assert set(body["roles"]) == ROLES
    assert body["overridden"] == []
    assert body["roles"]["judge_strong"]["model"] == "openrouter/google/gemini-2.5-flash-lite"

    put = await client.put(
        "/v1/settings/models",
        json={"roles": {"judge_strong": {"model": QWEN38, "reasoning": "low"}}},
    )
    assert put.status_code == 200
    got = (await client.get("/v1/settings/models")).json()
    assert got["roles"]["judge_strong"] == {"model": QWEN38, "reasoning": "low"}
    assert got["overridden"] == ["judge_strong"]
    assert got["roles"]["simulator"]["model"] == "openrouter/qwen/qwen3.7-flash"

    reset = await client.put("/v1/settings/models", json={"roles": {}})
    assert reset.json()["overridden"] == []
    again = (await client.get("/v1/settings/models")).json()
    assert again["roles"]["judge_strong"]["model"] == "openrouter/google/gemini-2.5-flash-lite"


@pytest.mark.integration
@pytest.mark.parametrize(
    "roles",
    [
        {"judge_strong": {"model": "openrouter/openai/gpt-5", "reasoning": "off"}},
        {"judge_strong": {"model": "openrouter/anthropic/claude-x", "reasoning": "off"}},
        {"embedder": {"model": QWEN38, "reasoning": "off"}},
        {"judge_strong": {"model": QWEN38, "reasoning": "max"}},
    ],
)
async def test_put_rejects_models_outside_the_catalog_and_bad_values(client, roles):
    r = await client.put("/v1/settings/models", json={"roles": roles})
    assert r.status_code == 422, r.text
    assert (await client.get("/v1/settings/models")).json()["overridden"] == []


@pytest.mark.integration
async def test_run_manifest_records_workspace_models(client):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    await client.put(
        "/v1/settings/models",
        json={"roles": {"judge_small": {"model": QWEN38, "reasoning": "off"}}},
    )
    r = await client.post(
        "/v1/runs",
        json={
            "suite_id": seed["suite_id"],
            "agent_version_id": seed["agent_version_id"],
            "budget_usd_micros": 2_000_000,
        },
    )
    assert r.status_code == 201, r.text
    roles = r.json()["manifest"]["model_roles"]
    assert roles["judge_small"] == QWEN38
    assert roles["simulator"] == "openrouter/qwen/qwen3.7-flash"
    got = (await client.get(f"/v1/runs/{r.json()['id']}")).json()
    assert got["manifest"]["model_roles"]["judge_small"] == QWEN38


def test_gateway_for_roles_uses_the_runs_models_and_shares_the_limiter():
    base = LiteLLMGateway(GatewayConfig())
    g = gateway_for_roles(base, {"judge_small": {"model": QWEN38, "reasoning": "high"}})
    assert isinstance(g, LiteLLMGateway) and g is not base
    assert g.limiter is base.limiter
    assert g.config.llm.roles["judge_small"].model == QWEN38
    assert g.config.llm.roles["judge_small"].reasoning == "high"
    assert g.config.llm.roles["simulator"].model == base.config.llm.roles["simulator"].model


def test_gateway_for_roles_leaves_scripted_gateways_and_empty_settings_alone():
    scripted = ScriptedLLM({})
    choice = {"judge_small": {"model": QWEN38, "reasoning": "off"}}
    assert gateway_for_roles(scripted, choice) is scripted
    base = LiteLLMGateway(GatewayConfig())
    assert gateway_for_roles(base, None) is base
