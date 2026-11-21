from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC).replace(microsecond=0)


def rec(i: int, **kw) -> dict:
    base = {
        "id": f"gdc_{i:04d}",
        "ts": (NOW - timedelta(seconds=100 - i)).isoformat(),
        "session_id": "ses_1",
        "policy_id": "pol_a",
        "policy_version": 1,
        "mode": "enforce",
        "kind": "tool_call",
        "tool": "issue_refund",
        "args": {"amount_cents": 5},
        "action": "allow",
        "enforced": True,
        "overhead_us": 100,
    }
    return {**base, **kw}


async def post(client, *records):
    return await client.post("/v1/gateway/decisions", json={"records": list(records)})


async def test_batch_ingest_is_idempotent_and_capped(client):
    r = await post(client, rec(1), rec(2), rec(3))
    assert r.status_code == 202 and r.json() == {"accepted": 3, "duplicates": 0}
    again = await post(client, rec(2), rec(3), rec(4))
    assert again.json() == {"accepted": 1, "duplicates": 2}
    assert (await post(client)).json() == {"accepted": 0, "duplicates": 0}
    big = await post(client, *[rec(1000 + i) for i in range(501)])
    assert big.status_code == 422
    ok = await post(client, *[rec(2000 + i) for i in range(500)])
    assert ok.json()["accepted"] == 500
    bad = await post(client, {**rec(9), "action": "explode"})
    assert bad.status_code == 422


async def test_filters_and_pagination(client):
    await post(
        client,
        rec(1, action="block", rule_id="refund-cap", severity="critical"),
        rec(2, mode="shadow", enforced=False, would_have="block", rule_id="refund-cap"),
        rec(3, tool="lookup_order"),
        rec(4, policy_id="pol_b", action="log", rule_id="audit"),
        rec(5, kind="output", tool=None, action="redact", rule_id="pii"),
    )

    async def ids(**params):
        r = await client.get("/v1/gateway/decisions", params=params)
        assert r.status_code == 200, r.text
        return [x["id"] for x in r.json()["items"]]

    assert await ids() == [f"gdc_000{i}" for i in (5, 4, 3, 2, 1)]  # newest first
    assert await ids(action="block") == ["gdc_0001"]
    assert await ids(rule_id="refund-cap") == ["gdc_0002", "gdc_0001"]
    assert await ids(tool="lookup_order") == ["gdc_0003"]
    assert await ids(mode="shadow") == ["gdc_0002"]
    assert await ids(enforced="false") == ["gdc_0002"]
    assert await ids(policy_id="pol_b") == ["gdc_0004"]
    assert await ids(policy_id="pol_b", action="block") == []
    lo = (NOW - timedelta(seconds=97)).isoformat()
    hi = (NOW - timedelta(seconds=96)).isoformat()
    assert await ids(**{"from": lo, "to": hi}) == ["gdc_0004", "gdc_0003"]

    page1 = (await client.get("/v1/gateway/decisions", params={"limit": 2})).json()
    assert [x["id"] for x in page1["items"]] == ["gdc_0005", "gdc_0004"] and page1["next_cursor"]
    page2 = (
        await client.get(
            "/v1/gateway/decisions", params={"limit": 2, "cursor": page1["next_cursor"]}
        )
    ).json()
    assert [x["id"] for x in page2["items"]] == ["gdc_0003", "gdc_0002"]
    page3 = (
        await client.get(
            "/v1/gateway/decisions", params={"limit": 2, "cursor": page2["next_cursor"]}
        )
    ).json()
    assert [x["id"] for x in page3["items"]] == ["gdc_0001"] and page3["next_cursor"] is None
    item = page3["items"][0]
    assert item["rule_id"] == "refund-cap" and item["args"] == {"amount_cents": 5}


async def test_stats_percentiles_on_known_overheads(client):
    records = [rec(i, overhead_us=us) for i, us in enumerate([100, 200, 300, 400, 500], start=1)]
    records.append(rec(6, action="block", rule_id="refund-cap", overhead_us=300))
    records.append(rec(7, action="block", rule_id="refund-cap", overhead_us=300))
    records.append(rec(8, action="redact", rule_id="pii", overhead_us=300))
    await post(client, *records)
    old = rec(99, ts=(NOW - timedelta(days=3)).isoformat(), overhead_us=900_000)
    await post(client, old)

    st = (await client.get("/v1/gateway/stats", params={"window": "1h"})).json()
    assert st["window_s"] == 3600 and st["total"] == 8  # the 3-day-old record is outside
    assert st["by_action"] == {"allow": 5, "block": 2, "redact": 1}
    assert {(r["rule_id"], r["action"]): r["count"] for r in st["by_rule"]} == {
        (None, "allow"): 5,
        ("refund-cap", "block"): 2,
        ("pii", "redact"): 1,
    }
    ov = st["overhead_us"]
    assert ov["p50"] == 300
    assert ov["p95"] == pytest.approx(465) and ov["p99"] == pytest.approx(493)
    day = st["by_day"]
    assert {(d["rule_id"], d["action"], d["count"]) for d in day} == {
        ("refund-cap", "block", 2),
        ("pii", "redact", 1),
    }
    wide = (await client.get("/v1/gateway/stats", params={"window": "7d"})).json()
    assert wide["total"] == 9 and wide["overhead_us"]["p99"] > 500
    empty = (await client.get("/v1/gateway/stats", params={"window": "1s"})).json()
    assert empty["total"] == 0 and empty["overhead_us"]["p50"] is None
    assert (await client.get("/v1/gateway/stats", params={"window": "soon"})).status_code == 422


async def test_decisions_are_workspace_scoped(client, sm):
    await post(client, rec(1))
    async with sm() as s, s.begin():
        await s.execute(text("INSERT INTO workspaces (id, name) VALUES ('ws_other', 'o')"))
        await s.execute(text("UPDATE gateway_decisions SET workspace_id = 'ws_other'"))
    assert (await client.get("/v1/gateway/decisions")).json()["items"] == []
    assert (await client.get("/v1/gateway/stats")).json()["total"] == 0
