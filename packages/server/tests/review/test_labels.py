"""Human labels: verdict row, report preference, outcome recompute, upsert, audit."""

from __future__ import annotations

import pytest
from gauntlet_core.eval import RunReport
from review_helpers import HARD
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def seeded_episode(client) -> tuple[str, str]:
    await client.post("/v1/rubrics", json=HARD)
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    eps = (
        await client.get(f"/v1/runs/{seed['run_id']}/episodes", params={"outcome": "passed"})
    ).json()
    return seed["run_id"], eps["items"][0]["id"]


async def label(client, ep: str, result: str, rubric: str = "rb_hard", note: str | None = None):
    return await client.post(
        "/v1/review/labels",
        json={"episode_id": ep, "rubric_id": rubric, "result": result, "note": note},
    )


async def test_label_writes_a_human_verdict_and_recomputes_the_outcome(client, sm):
    _, ep = await seeded_episode(client)
    r = await label(client, ep, "fail", note="broke it")
    assert r.status_code == 200, r.text
    out = r.json()
    assert (out["outcome_before"], out["outcome_after"]) == ("passed", "failed")
    async with sm() as s:
        row = (
            await s.execute(
                text(
                    "SELECT evaluator, result, doc->>'stage' AS stage, (doc->>'confidence')::float "
                    "AS conf FROM verdicts WHERE episode_id = :e AND criterion = 'rb_hard'"
                ),
                {"e": ep},
            )
        ).one()
        outcome = (
            await s.execute(text("SELECT outcome FROM episodes WHERE id = :e"), {"e": ep})
        ).scalar()
        events = (
            await s.execute(text("SELECT count(*) FROM events WHERE episode_id = :e"), {"e": ep})
        ).scalar()
    assert tuple(row) == ("human:t", "fail", "human", 1.0)
    assert outcome == "failed" and events > 0
    detail = (await client.get(f"/v1/episodes/{ep}")).json()
    assert detail["outcome"] == "failed"
    human = [v for v in detail["verdicts"] if v["criterion"] == "rb_hard"]
    assert [v["stage"] for v in human] == ["human"]
    audit = (await client.get("/v1/audit")).json()["items"]
    assert any(a["action"] == "review.labeled" and a["subject_id"] == ep for a in audit)


async def test_report_prefers_the_human_row_and_counts_overrides(client, sm):
    run_id, ep = await seeded_episode(client)
    before = RunReport.model_validate((await client.get(f"/v1/runs/{run_id}/report")).json())
    assert before.human_overridden == 0
    # a judge verdict for the same criterion exists first, then the human disagrees
    async with sm() as s, s.begin():
        await s.execute(
            text(
                "INSERT INTO verdicts (id, workspace_id, episode_id, evaluator, criterion, "
                "result, doc) VALUES ('vrd_j', 'ws_test', :e, 'judge:rb_hard', 'rb_hard', 'pass', "
                "CAST(:d AS jsonb))"
            ),
            {
                "e": ep,
                "d": '{"evaluator":"judge:rb_hard","criterion":"rb_hard","result":"pass",'
                '"stage":"small","confidence":0.9}',
            },
        )
    await label(client, ep, "fail")
    rep = RunReport.model_validate((await client.get(f"/v1/runs/{run_id}/report")).json())
    dim = next(d for d in rep.dimensions if d.criterion == "rb_hard")
    assert (dim.passed, dim.failed) == (0, 1)  # the judge's pass no longer counts
    assert rep.human_overridden == 1
    assert rep.pass_rate is not None and before.pass_rate is not None
    assert rep.pass_rate < before.pass_rate


async def test_relabel_is_an_idempotent_upsert_and_can_restore_the_outcome(client, sm):
    _, ep = await seeded_episode(client)
    await label(client, ep, "fail")
    again = (await label(client, ep, "fail")).json()
    assert again["outcome_after"] == "failed"
    async with sm() as s:
        n_labels = (await s.execute(text("SELECT count(*) FROM human_labels"))).scalar()
        n_rows = (
            await s.execute(text("SELECT count(*) FROM verdicts WHERE criterion = 'rb_hard'"))
        ).scalar()
    assert (n_labels, n_rows) == (1, 1)
    back = (await label(client, ep, "pass")).json()
    assert back["outcome_after"] == "passed"
    na = (await label(client, ep, "na")).json()
    assert na["outcome_after"] == "passed"


async def test_label_validation(client):
    _, ep = await seeded_episode(client)
    assert (await label(client, ep, "maybe")).status_code == 422
    assert (await label(client, "ep_nope", "pass")).status_code == 404
    assert (await label(client, ep, "pass", rubric="no_such_rubric")).status_code == 404
