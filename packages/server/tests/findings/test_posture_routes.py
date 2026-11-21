"""Posture and coverage endpoints over a real campaign against the vulnerable DVA."""

from __future__ import annotations

import pytest
from atk_helpers import attack, benign, make_agent_version, store_scenario, turn_attack
from gauntlet_server.services.attack_lib import upsert_attacks
from live_dva import live_stack, run_campaign
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def test_posture_for_a_vulnerable_then_fixed_version(client, state):
    flaws = {"F17"}
    async with live_stack(state, flaws) as url:
        agent, v1 = await make_agent_version(client, url, label="v1")
        await store_scenario(state, benign())
        async with state.sm() as s, s.begin():
            await upsert_attacks(s, "ws_test", [attack(), turn_attack()])
        await run_campaign(state, client, v1, ["atk_dva_notes", "atk_turn_probe"])

        p = (await client.get(f"/v1/agents/{agent}/versions/{v1}/posture")).json()
        assert p["grade"] in ("F", "D") and p["grade"] == "F"
        assert p["grade_basis"][0].startswith("Grade F") and "Coverage" in p["grade_basis"][1]
        assert p["summary"]["open_by_severity"] == {"critical": 1}
        assert p["summary"]["attacks_run"] == 2 and p["summary"]["attack_success_rate"] == 0.5
        cells = {(c["category"], c["vector"]): c for c in p["coverage"]}
        assert cells[("indirect_injection", "tool_result")]["successes"] == 1
        assert cells[("direct_injection", "user_turn")]["attempts"] == 1
        assert cells[("jailbreak", "user_turn")]["attempts"] == 0  # gaps are explicit
        refund = next(t for t in p["tool_review"] if t["tool"] == "issue_refund")
        assert refund["over_privileged"] and refund["tainted_calls"] == 1
        untouched = next(t for t in p["tool_review"] if t["tool"] == "create_return_label")
        assert untouched["reasons"] == ["not exercised"] and not untouched["over_privileged"]
        assert p["top_findings"][0]["severity"] == "critical"
        assert p["recommendations"][0]["text"].startswith("Treat tool output as untrusted")
        assert p["previous"] is None
        owasp = {r["id"]: r for r in p["compliance"]}
        assert owasp["LLM01"]["attempts"] == 2 and owasp["LLM01"]["findings"] == 1

        md = (await client.get(f"/v1/agents/{agent}/versions/{v1}/posture?format=md")).text
        assert md.startswith(f"# Security posture: {v1}") and "Grade: **F**" in md
        assert "## Coverage" in md and "issue_refund" in md and "## Recommendations" in md
        heat = (await client.get(f"/v1/agents/{agent}/versions/{v1}/coverage")).json()
        assert heat["agent_version_id"] == v1 and len(heat["coverage"]) == len(p["coverage"])

        # a later version with the flaw off: the finding is gone and the comparison says so
        flaws.clear()
        _, v2 = await make_agent_version(client, url, agent_id=agent, label="v2")
        await run_campaign(state, client, v2, ["atk_dva_notes", "atk_turn_probe"])
        q = (await client.get(f"/v1/agents/{agent}/versions/{v2}/posture")).json()
        assert q["grade"] == "B"  # no findings, but coverage is below the threshold
        assert q["previous"] == {
            "version_id": v1,
            "grade": "F",
            "new": 0,
            "fixed": 1,
            "unchanged": 0,
        }
        same = (
            await client.get(f"/v1/agents/{agent}/versions/{v2}/posture?compare_to={v1}")
        ).json()
        assert same["previous"]["version_id"] == v1
        card = next(d for d in same["data_exposure"] if d["canary_id"] == "card_main")
        assert card["planted_episodes"] == 2 and card["leaked_episodes"] == 0


async def test_unknown_and_cross_workspace_versions_are_404(client, state):
    agent, v1 = await make_agent_version(client, "http://localhost:9/v1")
    assert (await client.get(f"/v1/agents/{agent}/versions/nope/posture")).status_code == 404
    assert (await client.get(f"/v1/agents/other/versions/{v1}/posture")).status_code == 404
    assert (await client.get(f"/v1/agents/{agent}/versions/{v1}/coverage")).status_code == 200
    bad = await client.get(f"/v1/agents/{agent}/versions/{v1}/posture?compare_to=nope")
    assert bad.status_code == 404
    async with state.sm() as s, s.begin():
        await s.execute(
            text(
                "INSERT INTO workspaces (id, name) VALUES ('ws_other', 'o') ON CONFLICT DO NOTHING"
            )
        )
        await s.execute(text("UPDATE agent_versions SET workspace_id = 'ws_other'"))
    assert (await client.get(f"/v1/agents/{agent}/versions/{v1}/posture")).status_code == 404
