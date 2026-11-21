"""Cross-run stability of one scenario and the quarantine suggestion."""

from __future__ import annotations

import pytest
from api_helpers import new_run
from gauntlet_server.services.stability import StabilityOut
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def test_stability_history_of_the_same_agent_version(client, state, sm):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    second = await new_run(client, state, seed)
    r = await client.get(
        "/v1/scenarios/scn_ecom_07/stability",
        params={"agent_version_id": seed["agent_version_id"], "limit": 10},
    )
    assert r.status_code == 200, r.text
    out = StabilityOut.model_validate(r.json())
    assert out.runs[0].run_id == second  # newest first
    assert {h.run_id for h in out.runs} == {seed["run_id"], second}
    assert all(h.counted == 1 and h.rate == 0.0 and not h.flaky for h in out.runs)
    assert out.suggestion is None and not out.quarantined


async def test_flaky_history_produces_a_suggestion_and_limit_applies(client, state, sm):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    ids = [seed["run_id"]]
    for _ in range(3):
        ids.append(await new_run(client, state, seed, repetitions=3))
    for rid in ids[1:]:  # make scn_ecom_03 mixed (flaky) in three completed runs
        async with sm() as s, s.begin():
            await s.execute(
                text(
                    "UPDATE episodes SET outcome = 'failed' WHERE run_id = :r "
                    "AND scenario_id = 'scn_ecom_03' AND rep = 0"
                ),
                {"r": rid},
            )
    out = StabilityOut.model_validate(
        (
            await client.get(
                "/v1/scenarios/scn_ecom_03/stability",
                params={"agent_version_id": seed["agent_version_id"]},
            )
        ).json()
    )
    assert sum(h.flaky for h in out.runs) == 3
    assert out.suggestion is not None and out.suggestion.kind == "flaky"
    assert "3 of the last 4 runs" in out.suggestion.reason
    limited = (
        await client.get(
            "/v1/scenarios/scn_ecom_03/stability",
            params={"agent_version_id": seed["agent_version_id"], "limit": 2},
        )
    ).json()
    assert len(limited["runs"]) == 2
    assert (await client.get("/v1/scenarios/nope/stability")).status_code == 404


async def test_auto_quarantine_applies_suggestions_only_when_enabled(client, state, sm):
    from gauntlet_server.services.stability import auto_quarantine_for_run

    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    ids = [seed["run_id"]]
    for _ in range(3):
        ids.append(await new_run(client, state, seed, repetitions=3))
    for rid in ids[1:]:
        async with sm() as s, s.begin():
            await s.execute(
                text(
                    "UPDATE episodes SET outcome = 'failed' WHERE run_id = :r "
                    "AND scenario_id = 'scn_ecom_03' AND rep = 0"
                ),
                {"r": rid},
            )
    async with sm() as s, s.begin():
        assert await auto_quarantine_for_run(s, ids[-1]) == []  # the setting is off by default
        await s.execute(
            text(
                "INSERT INTO workspace_settings (workspace_id, doc) "
                "VALUES ('ws_test', CAST(:d AS jsonb)) "
                "ON CONFLICT (workspace_id) DO UPDATE SET doc = EXCLUDED.doc"
            ),
            {"d": '{"auto_quarantine": true}'},
        )
    async with sm() as s, s.begin():
        assert await auto_quarantine_for_run(s, ids[-1]) == ["scn_ecom_03"]
    out = (
        await client.get(
            "/v1/scenarios/scn_ecom_03/stability",
            params={"agent_version_id": seed["agent_version_id"]},
        )
    ).json()
    assert out["quarantined"] and out["quarantine_reason"].startswith("auto: flaky")
    audit = (await client.get("/v1/audit")).json()["items"]
    assert any(a["action"] == "scenario.quarantined" and a["actor"] == "system" for a in audit)
