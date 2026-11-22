"""Enforcement gate, policy tests listing, blast radius and permission diff (no live agent)."""

from __future__ import annotations

import json

import pytest
from policy_helpers import compile_seeded
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def accepted_policy(client, state) -> dict:
    started = await compile_seeded(client, state)
    pid = started["policy_id"]
    props = (await client.get(f"/v1/policies/{pid}/proposals")).json()["proposals"]
    first = next(p["clause_id"] for p in props if p["klass"] == "machine")
    r = await client.patch(f"/v1/policies/{pid}/proposals/{first}", json={"status": "accepted"})
    assert r.status_code == 200
    pub = await client.post(f"/v1/policies/{pid}/publish")  # shadow v1
    assert pub.status_code == 201 and pub.json()["policy"]["mode"] == "shadow"
    return {"policy_id": pid, "seed": started["seed"]}


async def add_test(sm, ws_seed: dict, policy_id: str, version: int, **result) -> str:
    async with sm() as s, s.begin():
        tid = f"ptest_{policy_id[-6:]}{version}{len(result)}"
        await s.execute(
            text(
                "INSERT INTO policy_tests (id, workspace_id, policy_id, policy_version, "
                "agent_version_id, status, result, attack_count, benign_count, finished_at) "
                "VALUES (:i, 'ws_test', :p, :v, :a, 'done', CAST(:r AS jsonb), 5, 20, now())"
            ),
            {
                "i": tid, "p": policy_id, "v": version, "a": ws_seed["agent_version_id"],
                "r": json.dumps(result),
            },
        )  # fmt: skip
    return tid


async def test_enforce_needs_a_test_and_checks_the_numbers(client, state, sm):
    ctx = await accepted_policy(client, state)
    pid, seed = ctx["policy_id"], ctx["seed"]
    url = f"/v1/policies/{pid}/enforce"

    missing = await client.post(url)
    assert missing.status_code == 409 and missing.json()["error"]["code"] == "policy_test_required"
    assert missing.json()["error"]["detail"]["max_fp_rate"] == 0.02

    await add_test(sm, seed, pid, 1, fp_rate=0.10, block_rate=0.9)
    high_fp = await client.post(url)
    assert high_fp.status_code == 409
    err = high_fp.json()["error"]
    assert err["code"] == "policy_test_failed" and err["detail"]["fp_rate"] == 0.10

    await add_test(sm, seed, pid, 1, fp_rate=0.0, block_rate=0.2, note="low")
    low_block = await client.post(url)  # the newest test decides
    assert low_block.status_code == 409 and low_block.json()["error"]["detail"]["block_rate"] == 0.2

    await add_test(sm, seed, pid, 1, fp_rate=0.01, block_rate=0.8, note="ok", more=1)
    ok = await client.post(url)
    assert ok.status_code == 201, ok.text
    body = ok.json()
    assert body["policy"]["mode"] == "enforce" and body["status"] == "published"
    assert body["version"] == 2  # v1 was already published (shadow)
    assert (await client.get(f"/v1/policies/{pid}?version=1")).json()["policy"]["mode"] == "shadow"


async def test_override_bypasses_the_gate_and_is_audited(client, state, sm):
    ctx = await accepted_policy(client, state)
    pid = ctx["policy_id"]
    r = await client.post(f"/v1/policies/{pid}/enforce", json={"override": True})
    assert r.status_code == 201 and r.json()["policy"]["mode"] == "enforce"
    async with sm() as s:
        actions = [
            a
            for (a,) in (
                await s.execute(
                    text("SELECT action FROM audit_log WHERE subject_id = :p ORDER BY seq"),
                    {"p": pid},
                )
            ).all()
        ]
    assert "policy.enforce_override" in actions and "policy.enforced" in actions


async def test_tests_listing_and_scoping(client, state, sm):
    ctx = await accepted_policy(client, state)
    pid, seed = ctx["policy_id"], ctx["seed"]
    tid = await add_test(sm, seed, pid, 1, fp_rate=0.0, block_rate=1.0)
    listed = (await client.get(f"/v1/policies/{pid}/tests")).json()
    assert [t["id"] for t in listed] == [tid] and listed[0]["status"] == "done"
    one = (await client.get(f"/v1/policy-tests/{tid}")).json()
    assert one["result"]["block_rate"] == 1.0 and one["policy_version"] == 1
    assert (await client.get("/v1/policy-tests/ptest_nope")).status_code == 404
    bad = await client.post(
        f"/v1/policies/{pid}/test", json={"agent_version_id": "nope", "max_benign": 5}
    )
    assert bad.status_code == 404
    body = {"agent_version_id": seed["agent_version_id"]}
    assert (await client.post("/v1/policies/pol_nope/test", json=body)).status_code == 404
    async with sm() as s, s.begin():
        await s.execute(text("INSERT INTO workspaces (id, name) VALUES ('ws_other', 'o')"))
        await s.execute(text("UPDATE policy_tests SET workspace_id = 'ws_other'"))
    assert (await client.get(f"/v1/policy-tests/{tid}")).status_code == 404
    assert (await client.get(f"/v1/policies/{pid}/tests")).json() == []


async def test_blast_radius_shape_scoping_and_policy_effect(client, state, sm):
    ctx = await accepted_policy(client, state)
    seed = ctx["seed"]
    base = f"/v1/agents/{seed['agent_id']}/versions/{seed['agent_version_id']}/blast-radius"
    plain = (await client.get(base)).json()
    tools = {t["tool"]: t for t in plain["tools"]}
    assert {"issue_refund", "lookup_order", "apply_coupon"} <= set(tools)
    assert tools["issue_refund"]["risk"] == "financial"
    assert plain["exposure_score"] == plain["exposure_score_without_policy"] > 0
    assert tools["issue_refund"]["worst_case"].startswith("can move money")
    assert tools["lookup_order"]["calls_observed"] >= 0

    # a policy that covers issue_refund lowers the score
    pid = ctx["policy_id"]
    async with sm() as s, s.begin():
        await s.execute(
            text("UPDATE policies SET doc = CAST(:d AS jsonb) WHERE id = :p"),
            {
                "p": pid,
                "d": json.dumps(
                    {
                        "id": pid,
                        "version": 1,
                        "rules": [
                            {
                                "id": "r",
                                "description": "d",
                                "when": {"type": "tool_called", "tool": "issue_refund"},
                                "action": "require_approval",
                            }
                        ],
                    }
                ),
            },
        )
    covered = (await client.get(base, params={"policy_id": pid})).json()
    assert covered["exposure_score"] == plain["exposure_score"] - 3
    cov = {t["tool"]: t for t in covered["tools"]}["issue_refund"]
    assert cov["covered_by_rules"] == ["r"] and cov["approval_required"] is True
    assert (await client.get(base, params={"policy_id": "pol_nope"})).status_code == 404
    assert (
        await client.get(f"/v1/agents/{seed['agent_id']}/versions/nope/blast-radius")
    ).status_code == 404
    async with sm() as s, s.begin():
        await s.execute(text("INSERT INTO workspaces (id, name) VALUES ('ws_other', 'o')"))
        await s.execute(text("UPDATE agent_versions SET workspace_id = 'ws_other'"))
    assert (await client.get(base)).status_code == 404


async def test_permission_diff_between_two_versions(client, state):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    base = {
        "profile": {"purpose": "support"},
        "world_id": "ecommerce",
    }
    narrow = await client.post(
        f"/v1/agents/{seed['agent_id']}/versions",
        json={
            "label": "narrow",
            "target": {"kind": "hosted", "model": "m", "system_prompt": "p",
                       "tools": ["lookup_order"]},
            **base,
        },
    )  # fmt: skip
    assert narrow.status_code == 201, narrow.text
    wide = await client.post(
        f"/v1/agents/{seed['agent_id']}/versions",
        json={"label": "wide", "target": {"kind": "hosted", "model": "m", "system_prompt": "p"},
              **base},
    )  # fmt: skip
    d = (
        await client.get(
            f"/v1/agents/{seed['agent_id']}/permission-diff",
            params={"from": narrow.json()["id"], "to": wide.json()["id"]},
        )
    ).json()
    assert "issue_refund" in d["added_tools"] and d["removed_tools"] == []
    assert "issue_refund" in d["newly_uncovered"]  # no rule covers the new financial tool
    assert d["exposure_score_delta"] > 0
    back = (
        await client.get(
            f"/v1/agents/{seed['agent_id']}/permission-diff",
            params={"from": wide.json()["id"], "to": narrow.json()["id"]},
        )
    ).json()
    assert "issue_refund" in back["removed_tools"] and back["exposure_score_delta"] < 0
    missing = await client.get(
        f"/v1/agents/{seed['agent_id']}/permission-diff", params={"from": "x", "to": "y"}
    )
    assert missing.status_code == 404
