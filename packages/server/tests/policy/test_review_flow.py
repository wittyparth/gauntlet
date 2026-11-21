from __future__ import annotations

import pytest
from policy_helpers import compile_seeded
from sqlalchemy import text

pytestmark = pytest.mark.integration


def patch(client, pid, clause, **body):
    return client.patch(f"/v1/policies/{pid}/proposals/{clause}", json=body)


async def test_accept_reject_edit_publish_and_immutable_versions(client, state, sm):
    pid = (await compile_seeded(client, state))["policy_id"]
    props = (await client.get(f"/v1/policies/{pid}/proposals")).json()["proposals"]
    machine = [p["clause_id"] for p in props if p["klass"] == "machine"]
    model = next(p["clause_id"] for p in props if p["klass"] == "model")

    # publish needs at least one accepted proposal
    assert (await client.post(f"/v1/policies/{pid}/publish")).status_code == 422
    assert (await patch(client, pid, machine[0], status="accepted")).status_code == 200
    assert (await patch(client, pid, machine[1], status="rejected")).status_code == 200
    assert (await patch(client, pid, model, status="accepted")).status_code == 200

    # an invalid edit is a 422; a judge rule is not enforceable
    judge = {"id": "j", "description": "j", "when": {"type": "judge", "rubric": "x"}}
    r = await patch(client, pid, machine[2], status="accepted", rule=judge)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert (
        await patch(client, pid, machine[2], status="accepted", rule={"id": "x"})
    ).status_code == 422
    assert (await patch(client, pid, model, status="accepted", rule=judge)).status_code == 422
    assert (await patch(client, pid, "c99", status="accepted")).status_code == 404

    # a valid edit replaces the rule and marks it edited
    edit = {
        "id": "edited",
        "description": "d",
        "when": {"type": "tool_called", "tool": "issue_refund"},
        "action": "require_approval",
    }
    after = (await patch(client, pid, machine[2], status="accepted", rule=edit)).json()
    edited = next(p for p in after["proposals"] if p["clause_id"] == machine[2])
    assert edited["status"] == "edited" and edited["rule"]["id"] == "edited"

    pub = await client.post(f"/v1/policies/{pid}/publish")  # defaults: shadow, fail open
    assert pub.status_code == 201, pub.text
    v1 = pub.json()
    assert (v1["version"], v1["status"]) == (1, "published")
    assert (v1["policy"]["mode"], v1["policy"]["fail"]) == ("shadow", "open")
    assert [r["id"] for r in v1["policy"]["rules"]] == [
        next(p["rule"]["id"] for p in props if p["clause_id"] == machine[0]),
        "edited",
    ]

    # a mode change writes a new immutable version; v1 is untouched
    v2 = (
        await client.post(f"/v1/policies/{pid}/publish", json={"mode": "enforce", "fail": "closed"})
    ).json()
    assert (v2["version"], v2["policy"]["mode"], v2["policy"]["fail"]) == (2, "enforce", "closed")
    still = (await client.get(f"/v1/policies/{pid}?version=1")).json()
    assert still["policy"]["mode"] == "shadow" and still["status"] == "published"
    assert (await client.get(f"/v1/policies/{pid}")).json()["version"] == 2

    # editing a published policy creates draft version 3; published rows stay as they were
    await patch(client, pid, machine[3], status="accepted")
    latest = (await client.get(f"/v1/policies/{pid}")).json()
    assert (latest["version"], latest["status"]) == (3, "draft")
    assert (await client.get(f"/v1/policies/{pid}?version=2")).json()["status"] == "published"
    p3 = (await client.get(f"/v1/policies/{pid}/proposals?version=3")).json()["proposals"]
    p2 = (await client.get(f"/v1/policies/{pid}/proposals?version=2")).json()["proposals"]
    assert next(p for p in p3 if p["clause_id"] == machine[3])["status"] == "accepted"
    assert next(p for p in p2 if p["clause_id"] == machine[3])["status"] == "proposed"

    # audit rows for the published versions
    async with sm() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT detail FROM audit_log WHERE action = 'policy.published' "
                    "AND subject_id = :p ORDER BY seq"
                ),
                {"p": pid},
            )
        ).all()
    assert [r[0]["version"] for r in rows] == [1, 2]
    assert rows[0][0]["rule_ids"] == [r["id"] for r in v1["policy"]["rules"]]


async def test_rejecting_everything_blocks_publish(client, state):
    pid = (await compile_seeded(client, state))["policy_id"]
    await patch(client, pid, "c01", status="rejected")
    assert (await client.post(f"/v1/policies/{pid}/publish")).status_code == 422
    only_model = await patch(client, pid, "c03", status="accepted")  # c03 is a rubric clause
    assert only_model.status_code == 200
    r = await client.post(f"/v1/policies/{pid}/publish")
    assert r.status_code == 422 and r.json()["error"]["code"] == "no_accepted_proposals"
