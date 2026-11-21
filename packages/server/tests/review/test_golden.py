"""Golden sets: agreement, adjudication, counts, readiness, labeler kappa."""

from __future__ import annotations

import pytest
from review_helpers import synthetic_run
from sqlalchemy import text

pytestmark = pytest.mark.integration

RUBRIC = "task_completion"


async def label(client, ep: str, result: str, note: str | None = None):
    r = await client.post(
        "/v1/review/labels",
        json={"episode_id": ep, "rubric_id": RUBRIC, "result": result, "note": note},
    )
    assert r.status_code == 200, r.text


async def other_labeler(sm, ep: str, result: str, who: str = "u") -> None:
    async with sm() as s, s.begin():
        await s.execute(
            text(
                "INSERT INTO human_labels (id, workspace_id, episode_id, rubric_id, "
                "rubric_version, result, labeler) VALUES (:id, 'ws_test', :e, :r, 1, :res, :l)"
            ),
            {"id": f"hl_{who}_{ep}", "e": ep, "r": RUBRIC, "res": result, "l": who},
        )


async def twelve(client, sm):
    ids = await synthetic_run(
        sm, RUBRIC, [(f"scn_{i}", "pass", 0.9, None, "small") for i in range(12)]
    )
    mine = ["fail"] * 4 + ["pass"] * 8
    theirs = list(mine)
    theirs[0], theirs[11] = "pass", "fail"  # two conflicts
    for ep, a, b in zip(ids, mine, theirs, strict=True):
        await label(client, ep, a)
        await other_labeler(sm, ep, b)
    return ids


async def test_agreement_conflict_counts_and_readiness(client, sm):
    ids = await twelve(client, sm)
    r = await client.post(f"/v1/rubrics/{RUBRIC}/golden", json={"episode_ids": [*ids, "ep_none"]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["needs_adjudication"] == [ids[0], ids[11]]
    assert len(out["accepted"]) == 10 and out["missing"] == ["ep_none"]
    g = (await client.get(f"/v1/rubrics/{RUBRIC}/golden")).json()
    assert g["items"] == 10 and g["by_class"] == {"pass": 7, "fail": 3, "na": 0}
    assert g["labelers"] == 2 and g["needs_adjudication"] == [ids[0], ids[11]]
    assert g["ready"] is False and "10 of 40 items" in g["readiness"]
    (k,) = g["labeler_kappa"]
    assert k["labelers"] == ["t", "u"] and k["shared"] == 12 and 0 < k["kappa"] < 1


async def test_adjudicated_label_resolves_a_conflict(client, sm):
    ids = await twelve(client, sm)
    await client.post(f"/v1/rubrics/{RUBRIC}/golden", json={"episode_ids": ids})
    await label(client, ids[0], "fail", note="adjudicated: the refund was unauthorised")
    # a conflicting item stays out until it is accepted again
    g = (await client.get(f"/v1/rubrics/{RUBRIC}/golden")).json()
    assert g["items"] == 10 and ids[0] not in g["needs_adjudication"]
    out = (await client.post(f"/v1/rubrics/{RUBRIC}/golden", json={"episode_ids": [ids[0]]})).json()
    assert out["accepted"] == [ids[0]]
    g = (await client.get(f"/v1/rubrics/{RUBRIC}/golden")).json()
    assert g["items"] == 11 and g["by_class"]["fail"] == 4


async def test_readiness_when_big_enough(client, sm):
    spec = [(f"scn_{i % 5}", "pass", 0.9, None, "small") for i in range(44)]
    ids = await synthetic_run(sm, RUBRIC, spec)
    for i, ep in enumerate(ids):
        await label(client, ep, "fail" if i % 4 == 0 else "pass")
    await client.post(f"/v1/rubrics/{RUBRIC}/golden", json={"episode_ids": ids})
    g = (await client.get(f"/v1/rubrics/{RUBRIC}/golden")).json()
    assert g["ready"] is True and g["readiness"].startswith("ready: 44 items, 11 fail")
