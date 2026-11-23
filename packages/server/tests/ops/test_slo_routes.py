"""SLO CRUD, status from stored runs, interval-based breach."""

from __future__ import annotations

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def seed_agent(client):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    agent = (await client.get(f"/v1/agents/{seed['agent_id']}")).json()["id"]
    return seed, agent


async def set_outcomes(sm, run_id: str, passed: int) -> None:
    async with sm() as s, s.begin():
        await s.execute(
            text("UPDATE episodes SET outcome = 'failed', finished_at = now() WHERE run_id = :r"),
            {"r": run_id},
        )
        await s.execute(
            text(
                "UPDATE episodes SET outcome = 'passed' WHERE id IN "
                "(SELECT id FROM episodes WHERE run_id = :r ORDER BY id LIMIT :n)"
            ),
            {"r": run_id, "n": passed},
        )


async def make_slo(client, agent, **kw):
    body = {"agent_id": agent, "metric": "pass_rate", "objective": 0.9, "window_days": 7, **kw}
    r = await client.post("/v1/slos", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def test_crud_and_validation(client):
    _, agent = await seed_agent(client)
    slo = await make_slo(client, agent)
    assert slo["id"].startswith("slo_") and slo["burn_alerts"] == ["fast", "slow"]
    assert (await client.get(f"/v1/slos/{slo['id']}")).json()["objective"] == 0.9
    assert len((await client.get("/v1/slos")).json()) == 1
    p = await client.patch(f"/v1/slos/{slo['id']}", json={"objective": 0.8, "enabled": False})
    assert p.json()["objective"] == 0.8 and p.json()["enabled"] is False
    bad = await client.post(
        "/v1/slos", json={"agent_id": agent, "metric": "pass_rate", "objective": 0}
    )
    assert bad.status_code == 422
    assert (
        await client.post(
            "/v1/slos", json={"agent_id": "agent_nope", "metric": "pass_rate", "objective": 0.9}
        )
    ).status_code == 404
    assert (await client.delete(f"/v1/slos/{slo['id']}")).status_code == 204
    assert (await client.get(f"/v1/slos/{slo['id']}")).status_code == 404


async def test_changes_are_audited(client, sm):
    _, agent = await seed_agent(client)
    slo = await make_slo(client, agent)
    await client.delete(f"/v1/slos/{slo['id']}")
    async with sm() as s:
        actions = (
            (
                await s.execute(
                    text("SELECT action FROM audit_log WHERE subject_id = :i"), {"i": slo["id"]}
                )
            )
            .scalars()
            .all()
        )
    assert set(actions) == {"slo.create", "slo.delete"}


async def test_status_unknown_without_samples(client):
    _, agent = await seed_agent(client)
    slo = await make_slo(client, agent, metric="attack_success_rate", objective=0.1)
    st = (await client.get(f"/v1/slos/{slo['id']}/status")).json()
    assert st["state"] == "unknown" and st["value"] is None and st["n"] == 0


async def test_breach_needs_the_interval_to_exclude_the_objective(client, sm):
    seed, agent = await seed_agent(client)
    slo = await make_slo(client, agent)
    await set_outcomes(sm, seed["run_id"], 8)  # 8 of 10 against 0.9: warning only
    st = (await client.get(f"/v1/slos/{slo['id']}/status")).json()
    assert st["n"] == 10 and st["value"] == 0.8
    assert st["state"] == "warning" and not st["breached"] and st["warning"]
    await set_outcomes(sm, seed["run_id"], 3)  # 3 of 10: interval below 0.9
    st = (await client.get(f"/v1/slos/{slo['id']}/status")).json()
    assert st["state"] == "breached" and st["breached"]
    assert st["interval"][1] < 0.9 and st["error_budget_remaining"] < 0
    await set_outcomes(sm, seed["run_id"], 10)
    assert (await client.get(f"/v1/slos/{slo['id']}/status")).json()["state"] == "ok"


async def test_latency_slo_uses_p95_semantics(client, sm):
    seed, agent = await seed_agent(client)
    async with sm() as s, s.begin():
        await s.execute(
            text("UPDATE episodes SET finished_at = now(), latency_ms = 5000 WHERE run_id = :r"),
            {"r": seed["run_id"]},
        )
    slo = await make_slo(client, agent, metric="latency_p95", objective=1000)
    st = (await client.get(f"/v1/slos/{slo['id']}/status")).json()
    assert st["state"] == "breached" and st["value"] is None
