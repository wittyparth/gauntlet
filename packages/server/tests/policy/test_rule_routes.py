"""Rule-level editing of a policy draft: add, replace, delete (P4-6)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

RULE = {
    "id": "no-delete",
    "description": "Never delete an account",
    "severity": "critical",
    "when": {"type": "tool_called", "tool": "delete_account"},
    "action": "block",
}


@pytest.fixture
async def pid(client):
    await client.post("/v1/dev/seed", json={"reset": False, "gateway": True})
    return "pol_demo"


def rules(body: dict) -> dict[str, str]:
    return {p["rule"]["id"]: p["status"] for p in body["proposals"] if p["rule"]}


async def test_add_rule_creates_a_draft_with_an_accepted_proposal(client, pid):
    r = await client.post(f"/v1/policies/{pid}/rules", json=RULE)
    assert r.status_code == 201, r.text
    assert rules(r.json())["no-delete"] == "accepted"
    assert any(c["id"] == "rule_no-delete" for c in r.json()["clauses"])
    one = (await client.get(f"/v1/policies/{pid}")).json()
    assert (one["version"], one["status"]) == (2, "draft")  # the published v1 is untouched
    assert (await client.get(f"/v1/policies/{pid}?version=1")).json()["status"] == "published"
    pub = await client.post(f"/v1/policies/{pid}/publish", json={"mode": "shadow", "fail": "open"})
    assert pub.status_code == 201
    assert {r["id"] for r in pub.json()["policy"]["rules"]} == {
        "refund-cap",
        "no-card-email",
        "no-delete",
    }


async def test_duplicate_and_invalid_rules_are_rejected(client, pid):
    assert (await client.post(f"/v1/policies/{pid}/rules", json=RULE)).status_code == 201
    dup = await client.post(f"/v1/policies/{pid}/rules", json=RULE)
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "rule_exists"
    judge = {**RULE, "id": "j", "when": {"type": "judge", "rubric": "x"}}
    bad = await client.post(f"/v1/policies/{pid}/rules", json=judge)
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "validation_error"
    unknown = {**RULE, "id": "u", "when": {"type": "nope"}}
    assert (await client.post(f"/v1/policies/{pid}/rules", json=unknown)).status_code == 422


async def test_replace_and_delete(client, pid):
    edited = {**RULE, "id": "refund-cap", "severity": "low",
              "when": {"type": "tool_called", "tool": "issue_refund"}}  # fmt: skip
    r = await client.patch(f"/v1/policies/{pid}/rules/refund-cap", json=edited)
    assert r.status_code == 200 and rules(r.json())["refund-cap"] == "edited"
    mismatch = await client.patch(f"/v1/policies/{pid}/rules/refund-cap", json=RULE)
    assert mismatch.status_code == 422
    assert (
        await client.patch(f"/v1/policies/{pid}/rules/ghost", json={**RULE, "id": "ghost"})
    ).status_code == 404

    await client.post(f"/v1/policies/{pid}/rules", json=RULE)
    gone = await client.delete(f"/v1/policies/{pid}/rules/no-delete")
    assert gone.status_code == 200 and "no-delete" not in rules(gone.json())
    assert all(c["id"] != "rule_no-delete" for c in gone.json()["clauses"])
    rej = await client.delete(f"/v1/policies/{pid}/rules/no-card-email")
    assert rules(rej.json())["no-card-email"] == "rejected"  # a compiled clause stays, rejected
    assert (await client.delete(f"/v1/policies/{pid}/rules/ghost")).status_code == 404
