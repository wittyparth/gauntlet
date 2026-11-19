"""REST surface: auth, errors, CRUD, scoping, secrets, dry run."""

from __future__ import annotations

import pytest
from gauntlet_server.auth import hash_key
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def test_auth_and_error_envelope(client):
    r = await client.get("/v1/whoami")
    assert r.json()["workspace_id"] == "ws_test"
    r = await client.get("/v1/whoami", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
    assert "x-request-id" in r.headers
    r = await client.post("/v1/projects", json={"bad": 1})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    r = await client.get("/v1/projects/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


async def test_crud_flow_secrets_and_pagination(client):
    p = (await client.post("/v1/projects", json={"name": "P2"})).json()
    for i in range(3):
        await client.post("/v1/projects", json={"name": f"x{i}"})
    page = (await client.get("/v1/projects?limit=2")).json()
    assert len(page["items"]) == 2 and page["next_cursor"]
    rest = (await client.get(f"/v1/projects?limit=200&cursor={page['next_cursor']}")).json()
    assert {i["id"] for i in page["items"]}.isdisjoint(i["id"] for i in rest["items"])
    a = (await client.post("/v1/agents", json={"project_id": p["id"], "name": "A"})).json()
    body = {
        "label": "v1",
        "target": {
            "kind": "openai_compat",
            "base_url": "http://x/v1",
            "model": "m",
            "api_key_secret": "KEY1",
        },
        "profile": {"purpose": "p"},
    }
    r = await client.post(f"/v1/agents/{a['id']}/versions", json=body)
    assert r.status_code == 422  # secret reference not stored yet
    r = await client.post("/v1/secrets", json={"name": "KEY1", "value": "s3cret"})
    assert r.status_code == 201 and "s3cret" not in r.text
    assert "s3cret" not in (await client.get("/v1/secrets")).text
    v = await client.post(f"/v1/agents/{a['id']}/versions", json=body)
    assert v.status_code == 201
    assert (await client.get(f"/v1/agents/{a['id']}")).json()["latest_version_id"] == v.json()["id"]


async def test_workspace_scoping(client, sm):
    p = (await client.post("/v1/projects", json={"name": "mine"})).json()
    async with sm() as s, s.begin():
        await s.execute(text("INSERT INTO workspaces (id, name) VALUES ('ws_b', 'b')"))
        await s.execute(
            text(
                "INSERT INTO api_keys (id, workspace_id, hash, scopes) "
                "VALUES ('key_b', 'ws_b', :h, '[]')"
            ),
            {"h": hash_key("gk_b")},
        )
    r = await client.get(f"/v1/projects/{p['id']}", headers={"Authorization": "Bearer gk_b"})
    assert r.status_code == 404


async def test_scenarios_suites_and_dry_run(client):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    dry = await client.post(
        "/v1/runs?dry_run=true",
        json={
            "suite_id": seed["suite_id"],
            "agent_version_id": seed["agent_version_id"],
            "budget_usd_micros": 1_000_000,
        },
    )
    assert dry.status_code == 200 and dry.json()["valid"] and dry.json()["episode_count"] == 10
    runs = (await client.get("/v1/runs")).json()["items"]
    assert [r["id"] for r in runs] == [seed["run_id"]]  # the dry run created nothing
    bad = await client.post("/v1/suites", json={"id": "s_x", "name": "x", "scenarios": ["nope"]})
    assert bad.status_code == 422
    drafts = (await client.get("/v1/scenarios?status=draft")).json()["items"]
    assert [s["id"] for s in drafts] == ["scn_draft_status"]
    ok = await client.post("/v1/scenarios/scn_draft_status/approve")
    assert ok.json()["status"] == "approved"


async def test_run_state_machine_and_dev_gate(client, state):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    body = {
        "suite_id": seed["suite_id"],
        "agent_version_id": seed["agent_version_id"],
        "budget_usd_micros": 1_000_000,
    }
    run = (await client.post("/v1/runs", json=body)).json()
    rid = run["id"]
    assert (await client.post(f"/v1/runs/{rid}/resume")).status_code == 409
    assert (await client.post(f"/v1/runs/{rid}/pause")).json()["status"] == "paused"
    assert (await client.post(f"/v1/runs/{rid}/resume")).json()["status"] == "running"
    cancelled = (await client.post(f"/v1/runs/{rid}/cancel")).json()
    assert cancelled["status"] == "cancelled" and cancelled["counts"]["cancelled"] == 10
    again = await client.post(f"/v1/runs/{rid}/cancel")
    assert again.status_code == 409 and again.json()["error"]["code"] == "run_not_active"
    import dataclasses

    import httpx
    from gauntlet_server.app import create_app

    prod = dataclasses.replace(state, settings=dataclasses.replace(state.settings, env="prod"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(prod)),
        base_url="http://api.test",
        headers={"Authorization": "Bearer gk_test_key"},
    ) as c:
        assert (await c.post("/v1/dev/seed", json={})).status_code == 404
