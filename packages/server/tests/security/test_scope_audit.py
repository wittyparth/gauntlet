"""Attack scope limits and the hash-chained audit log."""

from __future__ import annotations

import asyncio

import pytest
from atk_helpers import make_attack_suite, make_version, run_body
from gauntlet_server.services.audit import audit, verify_chain
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.integration
LOCAL = "http://localhost:9/v1"


async def test_scope_defaults_and_each_violation_is_422_with_the_key(client, state):
    scope = (await client.get("/v1/settings/attack-scope")).json()
    assert scope == {
        "allowed_categories": None, "max_episodes_per_run": 2000,
        "max_run_budget_usd_micros": 20_000_000, "adaptive_enabled": True,
        "max_concurrent_attack_runs": 2,
    }  # fmt: skip
    version = await make_version(client, LOCAL)
    suite = await make_attack_suite(client, state)

    async def put(**kw):
        r = await client.put("/v1/settings/attack-scope", json={**scope, **kw})
        assert r.status_code == 200, r.text

    async def violated(**body) -> str:
        r = await client.post("/v1/runs", json=run_body(suite, version, **body))
        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "scope_violation"
        return str(r.json()["error"]["detail"]["key"])

    await put(allowed_categories=["exfiltration"])
    assert await violated() == "allowed_categories"
    await put(max_episodes_per_run=1)
    assert await violated(repetitions=2) == "max_episodes_per_run"
    await put(max_run_budget_usd_micros=500_000)
    assert await violated() == "max_run_budget_usd_micros"
    await put(max_concurrent_attack_runs=1)
    r = await client.post("/v1/runs", json=run_body(suite, version, budget_usd_micros=100))
    assert r.status_code == 201, r.text
    assert await violated(budget_usd_micros=100) == "max_concurrent_attack_runs"
    rows = (await client.get("/v1/audit?action=scope.updated")).json()["items"]
    assert len(rows) == 4  # every PUT is audited
    bad = await client.put("/v1/settings/attack-scope", json={**scope, "max_episodes_per_run": 0})
    assert bad.status_code == 422


async def test_attack_run_creation_is_audited_without_payload_text(client, state):
    version = await make_version(client, LOCAL)
    suite = await make_attack_suite(client, state)
    r = await client.post("/v1/runs", json=run_body(suite, version))
    assert r.status_code == 201
    rows = (await client.get("/v1/audit?action=attack_run.created")).json()["items"]
    assert [x["subject_id"] for x in rows] == [r.json()["id"]]
    assert "AGENT INSTRUCTION" not in str(rows)
    assert (await client.get("/v1/audit/verify")).json() == {
        "ok": True, "checked": 1, "first_bad_id": None,
    }  # fmt: skip


async def test_chain_verifies_tamper_detected_and_trigger_blocks_changes(client, state):
    for i in range(3):
        async with state.sm() as s, s.begin():
            await audit(s, "ws_test", "tester", "x.done", "thing", f"t{i}", {"n": i})
    assert (await verify_chain_ws(state)).ok
    async with state.sm() as s:
        with pytest.raises(DBAPIError, match="append-only"):
            await s.execute(text("UPDATE audit_log SET actor = 'evil'"))
        await s.rollback()
        with pytest.raises(DBAPIError, match="append-only"):
            await s.execute(text("DELETE FROM audit_log"))
        await s.rollback()
    async with state.sm() as s, s.begin():  # tamper as the table owner, bypassing the trigger
        await s.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_no_change"))
        bad = (
            await s.execute(
                text("UPDATE audit_log SET actor = 'evil' WHERE subject_id = 't1' RETURNING id")
            )
        ).scalar()
        await s.execute(text("ALTER TABLE audit_log ENABLE TRIGGER audit_log_no_change"))
    report = await verify_chain_ws(state)
    assert not report.ok and report.first_bad_id == bad and report.checked == 1
    out = (await client.get("/v1/audit/verify")).json()
    assert out["ok"] is False and out["first_bad_id"] == bad


async def test_concurrent_appends_keep_a_linear_chain(state):
    async def one(i: int) -> None:
        async with state.sm() as s, s.begin():
            await audit(s, "ws_test", "tester", "x.done", "thing", f"c{i}", {"i": i})

    await asyncio.gather(*(one(i) for i in range(20)))
    report = await verify_chain_ws(state)
    assert report.ok and report.checked == 20


async def verify_chain_ws(state):
    async with state.sm() as s:
        return await verify_chain(s, "ws_test")
