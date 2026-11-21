"""`effective_rubric` over the calibrations table: defaults, applied values, staleness."""

from __future__ import annotations

import json

import pytest
from gauntlet_server.services.calibration_state import effective_rubric
from sqlalchemy import text

pytestmark = pytest.mark.integration

RUBRIC = "task_completion"
MODELS = {"judge_small": "m/small", "judge_strong": "m/strong"}


async def add_calibration(
    sm, *, version=1, status="done", gating=True, tau=0.6, stale=False, models=MODELS, cid="cal_1"
):
    async with sm() as s, s.begin():
        await s.execute(
            text(
                "INSERT INTO calibrations (id, workspace_id, rubric_id, rubric_version, "
                "judge_models, status, gating_allowed, threshold, stale) VALUES "
                "(:id, 'ws_test', :r, :v, CAST(:m AS jsonb), :st, :g, :t, :stale)"
            ),
            {"id": cid, "r": RUBRIC, "v": version, "m": json.dumps(models), "st": status,
             "g": gating, "t": tau, "stale": stale},
        )  # fmt: skip


async def eff(sm, **kw):
    async with sm() as s:
        return await effective_rubric(s, "ws_test", RUBRIC, **kw)


async def test_uncalibrated_keeps_document_defaults(client, sm):
    await client.post("/v1/dev/seed", json={"reset": False})
    r = await eff(sm)
    assert (r.gating_allowed, r.threshold) == (False, 0.8)


async def test_calibrated_values_apply_and_only_finished_rows_count(client, sm):
    await client.post("/v1/dev/seed", json={"reset": False})
    await add_calibration(sm, status="running", tau=0.3, gating=True, cid="cal_run")
    assert not (await eff(sm)).gating_allowed  # unfinished rows are ignored
    await add_calibration(sm, tau=0.6)
    r = await eff(sm, models=MODELS)
    assert (r.gating_allowed, r.threshold) == (True, 0.6)


async def test_stale_flag_model_change_and_other_version_disable_gating(client, sm):
    await client.post("/v1/dev/seed", json={"reset": False})
    await add_calibration(sm)
    assert (await eff(sm, models=MODELS)).gating_allowed
    changed = {**MODELS, "judge_strong": "m/other"}
    assert not (await eff(sm, models=changed)).gating_allowed
    async with sm() as s, s.begin():
        await s.execute(text("UPDATE calibrations SET stale = true"))
    assert not (await eff(sm, models=MODELS)).gating_allowed
    async with sm() as s, s.begin():
        await s.execute(text("UPDATE calibrations SET stale = false, rubric_version = 2"))
    assert not (await eff(sm, models=MODELS)).gating_allowed  # calibrated another version


async def test_unknown_rubric_raises(client, sm):
    async with sm() as s:
        with pytest.raises(LookupError):
            await effective_rubric(s, "ws_test", "no_such")
