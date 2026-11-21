"""Review queue selection: reasons and order, exclusion, caps, blindness, reveal gate."""

from __future__ import annotations

import pytest
from review_helpers import synthetic_run
from sqlalchemy import text

pytestmark = pytest.mark.integration

RUBRIC = "task_completion"


def crafted():
    spec = []
    for i in range(9):  # disagreements: small said pass, strong said fail
        spec.append((f"scn_{i % 10}", "fail", 0.9, "pass", "strong"))
    for i in range(12):  # uncertain
        spec.append((f"scn_{i % 10}", "pass", 0.6, None, "small"))
    for i in range(30):  # confident: only eligible for the random share
        spec.append((f"scn_{i % 10}", "pass", 0.97, None, "small"))
    return spec


async def test_order_reasons_and_random_share(client, sm):
    await synthetic_run(sm, RUBRIC, crafted())
    r = await client.get("/v1/review/queue", params={"rubric": RUBRIC, "limit": 20})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    reasons = [i["reason"] for i in items]
    assert len(items) == 20
    assert reasons[:9] == ["disagreement"] * 9
    assert reasons[9:18] == ["uncertain"] * 9
    assert reasons[18:] == ["random"] * 2  # about 10 percent of the page
    random_eps = {i["episode_id"] for i in items if i["reason"] == "random"}
    assert all(int(e[-3:]) >= 21 for e in random_eps)  # drawn from the confident pool only


async def test_random_draw_is_stable_per_labeler_and_day(client, sm):
    await synthetic_run(sm, RUBRIC, crafted())
    a = (await client.get("/v1/review/queue", params={"rubric": RUBRIC})).json()["items"]
    b = (await client.get("/v1/review/queue", params={"rubric": RUBRIC})).json()["items"]
    assert a == b


async def test_items_are_blind_and_labelled_items_drop_out(client, sm):
    await synthetic_run(sm, RUBRIC, crafted())
    items = (await client.get("/v1/review/queue", params={"rubric": RUBRIC})).json()["items"]
    assert set(items[0]) == {"episode_id", "rubric_id", "rubric_version", "scenario_id", "reason"}
    first = items[0]["episode_id"]
    r = await client.post(
        "/v1/review/labels", json={"episode_id": first, "rubric_id": RUBRIC, "result": "fail"}
    )
    assert r.status_code == 200, r.text
    again = (await client.get("/v1/review/queue", params={"rubric": RUBRIC})).json()["items"]
    assert first not in {i["episode_id"] for i in again}
    # another labeler's queue still has it
    async with sm() as s, s.begin():
        await s.execute(text("UPDATE human_labels SET labeler = 'someone_else'"))
    again = (await client.get("/v1/review/queue", params={"rubric": RUBRIC})).json()["items"]
    assert first in {i["episode_id"] for i in again}


async def test_at_most_three_items_per_scenario(client, sm):
    spec = [("scn_a" if i % 2 else "scn_b", "fail", 0.9, "pass", "strong") for i in range(20)]
    await synthetic_run(sm, RUBRIC, spec)
    items = (await client.get("/v1/review/queue", params={"rubric": RUBRIC})).json()["items"]
    assert len(items) == 6
    for scn in ("scn_a", "scn_b"):
        assert sum(1 for i in items if i["scenario_id"] == scn) == 3


async def test_reveal_requires_a_label_first(client, sm):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    eps = (await client.get(f"/v1/runs/{seed['run_id']}/episodes")).json()["items"]
    ep = eps[0]["id"]
    url = f"/v1/review/items/{ep}/{RUBRIC}"
    blind = await client.get(url)
    assert blind.status_code == 200
    body = blind.json()
    assert body["judge"] is None and body["my_label"] is None and body["transcript"]
    assert "verdict" not in body["transcript"].lower().split("]")[0]
    denied = await client.get(url, params={"reveal": "true"})
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "label_first"
    await client.post(
        "/v1/review/labels", json={"episode_id": ep, "rubric_id": RUBRIC, "result": "pass"}
    )
    shown = (await client.get(url, params={"reveal": "true"})).json()
    assert shown["my_label"] == "pass" and shown["judge"]["criterion"] == RUBRIC
    assert shown["judge"]["stage"] != "human"
