"""Calibration job end to end with FakeLLM judges of known noise, drift and effective rubrics."""

from __future__ import annotations

import re

import pytest
from api_helpers import new_run
from gauntlet_core.eval import RunReport
from gauntlet_core.llm import FakeLLM, FakeReply
from gauntlet_core.schema import Cost
from gauntlet_server.services.calibration_state import effective_rubric
from gauntlet_server.services.jobs import run_job
from gauntlet_server.stores.jobs import PgJobQueue

pytestmark = pytest.mark.integration

RUBRIC = "task_completion"
AGENT_LINE = re.compile(r"^\[(\d+)\] AGENT: (.*)$", re.M)
QWEN38 = "openrouter/qwen/qwen3.8-flash"


def judge(truth: dict[str, str], wrong: set[str], conf_wrong: float):
    """A judge that answers from the first agent line of the transcript: right everywhere
    except on the scenarios in `wrong` (where it flips the answer with `conf_wrong`)."""

    def reply(messages) -> FakeReply:
        body = "\n".join(str(m["content"]) for m in messages)
        # rubric examples carry AGENT lines too: take the first one that is a known transcript
        seq, line = next(m for m in AGENT_LINE.findall(body) if m[1] in truth)
        answer = truth[line]
        flip = line in wrong
        if flip:
            answer = "pass" if answer == "fail" else "fail"
        ev = [{"seq": int(seq), "quote": line[:30]}] if answer == "fail" else []
        return FakeReply(
            parsed={
                "reasoning": "r",
                "evidence": ev,
                "result": answer,
                "confidence": conf_wrong if flip else 0.95,
            },
            cost=Cost(usd_micros=5),
        )

    return reply


async def first_agent_line(client, ep: str) -> str:
    item = (await client.get(f"/v1/review/items/{ep}/{RUBRIC}")).json()
    found = AGENT_LINE.search(item["transcript"])
    assert found is not None
    return found.group(2)


async def label_run(client, run_id: str, limit: int | None = None):
    eps = (await client.get(f"/v1/runs/{run_id}/episodes", params={"limit": 200})).json()["items"]
    eps = eps[:limit] if limit else eps
    lines = {e["id"]: await first_agent_line(client, e["id"]) for e in eps}
    distinct = sorted(set(lines.values()))
    fail_lines = set(distinct[: max(2, len(distinct) * 2 // 5)])
    truth = {ln: ("fail" if ln in fail_lines else "pass") for ln in distinct}
    for ep, ln in lines.items():
        r = await client.post(
            "/v1/review/labels",
            json={"episode_id": ep, "rubric_id": RUBRIC, "result": truth[ln]},
        )
        assert r.status_code == 200, r.text
    ids = list(lines)
    out = (await client.post(f"/v1/rubrics/{RUBRIC}/golden", json={"episode_ids": ids})).json()
    assert len(out["accepted"]) == len(ids)
    return truth, distinct


async def run_jobs(state) -> None:
    q = PgJobQueue(state.sm)
    for lease in await q.claim("test-worker", 10, 60):
        await run_job(state, q, lease)


async def test_calibration_gates_then_goes_stale_when_a_judge_model_changes(client, state, sm):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    run_id = await new_run(client, state, seed, repetitions=6)
    truth, distinct = await label_run(client, run_id)
    n = 60
    wrong = {distinct[-1]}  # the small judge is wrong on one scenario, with low confidence
    state.gateway = FakeLLM(
        by_role={
            "judge_small": [judge(truth, wrong, 0.6)] * (n + 5),
            "judge_strong": [judge(truth, set(), 0.95)] * (n + 5),
        }
    )

    before = RunReport.model_validate((await client.get(f"/v1/runs/{run_id}/report")).json())
    assert RUBRIC in before.caution.uncalibrated_rubrics

    r = await client.post(f"/v1/rubrics/{RUBRIC}/calibrate", json={})
    assert r.status_code == 202, r.text
    ids = r.json()
    job = (await client.get(f"/v1/jobs/{ids['job_id']}")).json()
    assert job["status"] == "queued"
    await run_jobs(state)
    job = (await client.get(f"/v1/jobs/{ids['job_id']}")).json()
    assert job["status"] == "done", job

    cal = (await client.get(f"/v1/calibrations/{ids['calibration_id']}")).json()
    res = cal["result"]
    assert cal["status"] == "done" and cal["golden_count"] == n
    assert res["n"] == n and res["n_pass"] + res["n_fail"] == n
    assert res["strong"]["kappa"] == 1.0 and res["small"]["kappa"] < 1.0
    assert res["gating_allowed"] is True and res["reasons"] == []
    assert cal["gating_allowed"] is True
    assert (
        res["chosen_tau"] == 0.7 and cal["threshold"] == 0.7
    )  # first tau that escalates the flips
    assert 0 < res["escalation_rate"] < 0.5
    taus = {p["tau"]: p for p in res["cascade_by_tau"]}
    assert taus[0.5]["kappa"] < taus[0.7]["kappa"] == 1.0
    assert cal["cost_usd_micros"] > 0 and res["cost_per_verdict_usd_micros"]["strong"] > 0
    listed = (await client.get(f"/v1/rubrics/{RUBRIC}/calibrations")).json()["items"]
    assert [c["id"] for c in listed] == [ids["calibration_id"]]

    # effective rubric and the report now see the calibrated values
    eff = await eff_rubric(state)
    assert eff.gating_allowed and eff.threshold == 0.7
    after = RunReport.model_validate((await client.get(f"/v1/runs/{run_id}/report")).json())
    assert RUBRIC not in after.caution.uncalibrated_rubrics
    assert next(d for d in after.dimensions if d.criterion == RUBRIC).gating_allowed

    # drift: nothing changed yet
    calm = (await client.post("/v1/calibrations/check-drift")).json()
    assert calm == {"stale": [], "enqueued": [], "skipped": []}
    # change a judge model: the calibration goes stale and a re-calibration is queued
    await client.put(
        "/v1/settings/models",
        json={"roles": {"judge_strong": {"model": QWEN38, "reasoning": "off"}}},
    )
    drift = (await client.post("/v1/calibrations/check-drift")).json()
    assert drift["stale"] == [ids["calibration_id"]] and len(drift["enqueued"]) == 1
    stale = (await client.get(f"/v1/calibrations/{ids['calibration_id']}")).json()
    assert stale["stale"] is True
    eff = await eff_rubric(state)
    assert not eff.gating_allowed
    again = RunReport.model_validate((await client.get(f"/v1/runs/{run_id}/report")).json())
    assert RUBRIC in again.caution.uncalibrated_rubrics
    assert (await client.post("/v1/calibrations/check-drift")).json()["stale"] == []  # idempotent


async def eff_rubric(state):
    async with state.sm() as s:
        return await effective_rubric(s, "ws_test", RUBRIC)


async def test_too_small_golden_set_completes_but_refuses_gating(client, state):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    run_id = seed["run_id"]
    truth, _ = await label_run(client, run_id)
    state.gateway = FakeLLM(
        by_role={
            "judge_small": [judge(truth, set(), 0.95)] * 40,
            "judge_strong": [judge(truth, set(), 0.95)] * 40,
        }
    )
    ids = (await client.post(f"/v1/rubrics/{RUBRIC}/calibrate", json={})).json()
    await run_jobs(state)
    cal = (await client.get(f"/v1/calibrations/{ids['calibration_id']}")).json()
    assert cal["status"] == "done" and cal["gating_allowed"] is False
    assert any("labelled items" in r and "< 40" in r for r in cal["result"]["reasons"])
    drift = (await client.post("/v1/calibrations/check-drift")).json()
    assert drift["enqueued"] == []  # models unchanged: nothing to do


async def test_calibrate_without_golden_items_is_rejected(client):
    await client.post("/v1/dev/seed", json={"reset": False})
    r = await client.post(f"/v1/rubrics/{RUBRIC}/calibrate", json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "no_golden_items"
    assert (await client.post("/v1/rubrics/nope/calibrate", json={})).status_code == 404
