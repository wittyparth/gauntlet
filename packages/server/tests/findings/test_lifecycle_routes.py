"""Findings lifecycle, list filters, pagination and workspace scoping."""

from __future__ import annotations

import pytest
from atk_helpers import add_finding, make_version

pytestmark = pytest.mark.integration
LOCAL = "http://localhost:9/v1"

LEGAL = {
    "open": {"triaged", "in_progress", "fixed", "accepted_risk", "false_positive"},
    "triaged": {"open", "in_progress", "fixed", "accepted_risk", "false_positive"},
    "in_progress": {"triaged", "fixed", "accepted_risk", "false_positive"},
    "fixed": {"open"},
    "verified": {"open"},
    "accepted_risk": {"open"},
    "false_positive": {"open"},
}
ALL = {"open", "triaged", "in_progress", "fixed", "verified", "accepted_risk", "false_positive"}


async def test_full_transition_table(client, state):
    version = await make_version(client, LOCAL)
    n = 0
    for frm, legal in LEGAL.items():
        for to in sorted(ALL - {frm}):
            n += 1
            fid = await add_finding(state, version, key=f"t{n}", status=frm)
            r = await client.patch(f"/v1/findings/{fid}", json={"status": to, "note": "because"})
            if to in legal:
                assert r.status_code == 200, (frm, to, r.text)
                assert r.json()["status"] == to
                assert r.json()["notes"][-1]["note"] == "because"
            else:
                assert r.status_code == 409, (frm, to)
                err = r.json()["error"]
                assert err["code"] == "illegal_transition"
                assert set(err["detail"]["allowed"]) == legal
    actions = (await client.get("/v1/audit?action=finding.status_changed&limit=1000")).json()
    assert len(actions["items"]) == 18  # one per legal transition
    bad = await add_finding(state, version, key="unk")
    assert (await client.patch(f"/v1/findings/{bad}", json={"status": "nope"})).status_code == 422


async def test_list_filters_pagination_and_scoping(client, state):
    version = await make_version(client, LOCAL)
    other = await make_version(client, LOCAL, label="v2")
    await add_finding(state, version, key="a", severity="critical")
    await add_finding(
        state, version, key="b", severity="low", category="exfiltration", title="Leak"
    )
    await add_finding(state, other, key="c", status="triaged")
    items = (await client.get("/v1/findings")).json()["items"]
    assert len(items) == 3
    assert len((await client.get("/v1/findings?severity=critical")).json()["items"]) == 1
    assert len((await client.get("/v1/findings?category=exfiltration")).json()["items"]) == 1
    assert len((await client.get("/v1/findings?status=triaged")).json()["items"]) == 1
    assert len((await client.get(f"/v1/findings?agent_version_id={other}")).json()["items"]) == 1
    assert [x["title"] for x in (await client.get("/v1/findings?q=leak")).json()["items"]] == [
        "Leak"
    ]
    page1 = (await client.get("/v1/findings?limit=2")).json()
    assert len(page1["items"]) == 2 and page1["next_cursor"]
    page2 = (await client.get(f"/v1/findings?limit=2&cursor={page1['next_cursor']}")).json()
    assert len(page2["items"]) == 1 and page2["next_cursor"] is None
    assert (await client.get("/v1/findings/fnd_missing")).status_code == 404
    assert (await client.post("/v1/findings/fnd_missing/pin")).status_code == 404


async def test_cross_workspace_findings_are_invisible(client, state):
    from sqlalchemy import text

    version = await make_version(client, LOCAL)
    fid = await add_finding(state, version, key="x")
    async with state.sm() as s, s.begin():
        await s.execute(
            text(
                "INSERT INTO workspaces (id, name) VALUES ('ws_other', 'o') ON CONFLICT DO NOTHING"
            )
        )
        await s.execute(text("UPDATE findings SET workspace_id = 'ws_other'"))
    assert (await client.get(f"/v1/findings/{fid}")).status_code == 404
    assert (await client.get("/v1/findings")).json()["items"] == []
