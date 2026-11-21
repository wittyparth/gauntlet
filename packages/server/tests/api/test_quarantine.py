"""Quarantine: the toggle, its audit row, and exclusion from the report headline."""

from __future__ import annotations

import pytest
from api_helpers import new_run
from gauntlet_core.eval import RunReport
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def test_quarantine_toggle_audit_and_report_exclusion(client, state, sm):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    run_id = seed["run_id"]
    before = RunReport.model_validate((await client.get(f"/v1/runs/{run_id}/report")).json())
    assert before.counted == 10 and before.quarantined == []

    r = await client.post(
        "/v1/scenarios/scn_ecom_07/quarantine", json={"on": True, "reason": "known flaky judge"}
    )
    assert r.status_code == 200, r.text
    assert (
        r.json()
        == {
            "scenario_id": "scn_ecom_07",
            "quarantined": True,
            "reason": "known flaky judge",
            "quarantined_at": r.json()["quarantined_at"],
        }
        and r.json()["quarantined_at"]
    )

    after = RunReport.model_validate((await client.get(f"/v1/runs/{run_id}/report")).json())
    assert after.quarantined == ["scn_ecom_07"] and after.counted == 9
    assert after.pass_rate == 1.0  # the failing scenario no longer drags the headline
    q = next(s for s in after.per_scenario if s.scenario_id == "scn_ecom_07")
    assert q.quarantined and q.rate == 0.0  # its own rate is still reported

    audit = (await client.get("/v1/audit")).json()
    actions = [a["action"] for a in audit["items"]]
    assert "scenario.quarantined" in actions

    off = await client.post(
        "/v1/scenarios/scn_ecom_07/quarantine", json={"on": False, "reason": "fixed"}
    )
    assert off.json()["quarantined"] is False
    assert (
        RunReport.model_validate((await client.get(f"/v1/runs/{run_id}/report")).json()).counted
        == 10
    )
    audit = (await client.get("/v1/audit")).json()
    assert "scenario.unquarantined" in [a["action"] for a in audit["items"]]


async def test_quarantined_scenario_still_runs_and_unknown_is_404(client, state):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    await client.post("/v1/scenarios/scn_ecom_07/quarantine", json={"on": True, "reason": "x"})
    run_id = await new_run(client, state, seed)
    run = (await client.get(f"/v1/runs/{run_id}")).json()
    assert run["counts"]["total"] == 10  # quarantined scenarios keep running
    rep = RunReport.model_validate((await client.get(f"/v1/runs/{run_id}/report")).json())
    assert rep.counted == 9 and rep.quarantined == ["scn_ecom_07"]
    missing = await client.post("/v1/scenarios/nope/quarantine", json={"on": True, "reason": "x"})
    assert missing.status_code == 404


async def test_new_scenario_version_stays_quarantined(client, sm):
    await client.post("/v1/dev/seed", json={"reset": False})
    await client.post("/v1/scenarios/scn_ecom_07/quarantine", json={"on": True, "reason": "x"})
    async with sm() as s:
        row = (
            await s.execute(
                text("SELECT bool_and(quarantined) FROM scenarios WHERE id = 'scn_ecom_07'")
            )
        ).scalar()
    assert row is True
