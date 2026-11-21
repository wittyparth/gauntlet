"""Migration report recommendations and Pareto data over the seeded demo suite."""

from __future__ import annotations

import pytest
from api_helpers import new_run
from sqlalchemy import text

pytestmark = pytest.mark.integration


@pytest.fixture
async def pair(client, state):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    agent_id = (await client.get("/v1/agents")).json()["items"][0]["id"]
    v2 = await client.post(
        f"/v1/agents/{agent_id}/versions",
        json={
            "label": "v2",
            "target": {"kind": "hosted", "model": "m2", "system_prompt": "You help with orders."},
            "profile": {"purpose": "orders"},
            "world_id": "ecommerce",
        },
    )
    assert v2.status_code == 201, v2.text
    cand = await new_run(client, state, seed, agent_version_id=v2.json()["id"])
    return seed, seed["run_id"], cand, v2.json()["id"]


async def mig(client, cand, base, **params):
    return await client.get(f"/v1/runs/{cand}/migration", params={"baseline": base, **params})


async def update(sm, sql, **kw):
    async with sm() as s, s.begin():
        await s.execute(text(sql), kw)


async def test_clean_candidate_is_safe_to_migrate(client, pair, sm):
    _, base, cand, _ = pair
    for r in (base, cand):
        await update(sm, "UPDATE episodes SET outcome = 'passed' WHERE run_id = :r", r=r)
    r = await mig(client, cand, base)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["recommendation"] == "safe_to_migrate", out["reasons"]
    assert out["compare"]["verdict"] == "no_detectable_change"
    assert out["candidate"]["episodes"] == out["baseline"]["episodes"] > 0
    assert out["candidate"]["cost_per_1000_episodes_usd"] == (
        out["candidate"]["cost_per_episode_usd_micros"] / 1000
    )
    assert out["candidate"]["agent_version_id"] != out["baseline"]["agent_version_id"]
    assert out["candidate"]["model"] == "m2" and out["cautions"] == []


async def test_regression_is_do_not_migrate(client, pair, sm):
    _, base, cand, _ = pair
    await update(sm, "UPDATE episodes SET outcome = 'failed' WHERE run_id = :r", r=cand)
    await update(sm, "UPDATE episodes SET outcome = 'passed' WHERE run_id = :r", r=base)
    out = (await mig(client, cand, base)).json()
    assert out["compare"]["verdict"] == "regression"
    assert out["recommendation"] == "do_not_migrate"
    assert any("regression" in r for r in out["reasons"])


async def test_new_critical_finding_blocks(client, pair, sm):
    _, base, cand, v2 = pair
    eps = (await client.get(f"/v1/runs/{cand}/episodes")).json()["items"]
    await update(
        sm,
        "INSERT INTO findings (id, workspace_id, agent_version_id, category, severity, dedup_key,"
        " title, attack_id, doc) VALUES ('fnd_c', 'ws_test', :v, 'inj', 'critical', 'fnd_c', 't',"
        " 'atk_x', '{}'::jsonb)",
        v=v2,
    )
    await update(
        sm,
        "INSERT INTO finding_episodes (finding_id, episode_id) VALUES ('fnd_c', :e)",
        e=eps[0]["id"],
    )
    out = (await mig(client, cand, base)).json()
    assert out["recommendation"] == "do_not_migrate"
    assert any("critical" in r for r in out["reasons"])
    assert out["candidate"]["open_findings_by_severity"] == {"critical": 1}


async def test_newly_failing_scenario_is_listed(client, pair, sm):
    _, base, cand, _ = pair
    await update(sm, "UPDATE episodes SET outcome = 'passed' WHERE run_id = :r", r=base)
    await update(
        sm,
        "UPDATE episodes SET outcome = 'failed' WHERE run_id = :r AND scenario_id = 'scn_ecom_03'",
        r=cand,
    )
    out = (await mig(client, cand, base)).json()
    assert out["recommendation"] != "safe_to_migrate"
    assert any("newly failing" in r and "scn_ecom_03" in r for r in out["reasons"])


def test_decision_table():
    from gauntlet_server.services.migration import decide

    off = {"blocking": False, "inconclusive": False, "newly_failing": False, "cost_up": False}
    assert decide(**off) == "safe_to_migrate"
    assert decide(**{**off, "blocking": True, "cost_up": True}) == "do_not_migrate"
    for k in ("inconclusive", "newly_failing", "cost_up"):
        assert decide(**{**off, k: True}) == "review"


async def test_cost_rise_needs_review(client, pair, sm):
    _, base, cand, _ = pair
    await update(
        sm,
        "UPDATE episodes SET cost_usd_micros = cost_usd_micros + 5000 WHERE run_id = :r",
        r=cand,
    )
    out = (await mig(client, cand, base)).json()
    assert out["recommendation"] == "review" and out["cost_change_pct"] > 0
    assert any("Cost per episode rose" in r for r in out["reasons"])


async def test_inconclusive_comparison_needs_review(client, pair, sm):
    _, base, cand, _ = pair
    await update(
        sm,
        "UPDATE episodes SET outcome = 'platform_error' WHERE run_id = :r AND id NOT IN "
        "(SELECT id FROM episodes WHERE run_id = :r ORDER BY id LIMIT 2)",
        r=cand,
    )
    out = (await mig(client, cand, base)).json()
    assert out["compare"]["verdict"] == "inconclusive", out["compare"]["verdict"]
    assert out["recommendation"] in ("review", "do_not_migrate")
    assert any("inconclusive" in r for r in out["reasons"])


async def test_incomparable_runs_422_and_force_cautions(client, pair, sm):
    _, base, cand, _ = pair
    await update(sm, "INSERT INTO suites (id, workspace_id, name) VALUES ('other', 'ws_test', 'o')")
    await update(sm, "UPDATE runs SET suite_id = 'other' WHERE id = :r", r=cand)
    r = await mig(client, cand, base)
    assert r.status_code == 422 and r.json()["error"]["code"] == "incomparable_runs"
    assert r.json()["error"]["detail"]["reasons"]
    forced = await mig(client, cand, base, force="true")
    assert forced.status_code == 200 and forced.json()["cautions"]


async def test_migration_is_workspace_scoped_and_needs_done_runs(client, state, pair, sm):
    seed, base, cand, _ = pair
    assert (await mig(client, cand, "run_nope")).status_code == 404
    queued = await new_run(client, state, seed, wait=False)
    assert (await mig(client, queued, base)).status_code == 409
    await update(sm, "INSERT INTO workspaces (id, name) VALUES ('ws_other', 'o')")
    await update(sm, "UPDATE runs SET workspace_id = 'ws_other' WHERE id = :r", r=base)
    assert (await mig(client, cand, base)).status_code == 404


async def test_pareto_marks_dominated_with_interval_support(client, pair, sm):
    _, base, cand, _ = pair
    await update(
        sm,
        "UPDATE episodes SET cost_usd_micros = cost_usd_micros + 9000 WHERE run_id = :r",
        r=cand,
    )
    await update(
        sm,
        "UPDATE episodes SET outcome = 'failed' WHERE run_id = :r AND scenario_id <> 'scn_ecom_03'",
        r=cand,
    )
    await update(sm, "UPDATE episodes SET outcome = 'passed' WHERE run_id = :r", r=base)
    r = await client.get("/v1/migrations/pareto", params={"run_ids": f"{base},{cand}"})
    assert r.status_code == 200, r.text
    out = r.json()
    pts = {p["run_id"]: p for p in out["points"]}
    assert out["metrics"] == ["pass_rate", "cost"]
    assert pts[base]["on_frontier"] and not pts[cand]["on_frontier"]
    assert pts[cand]["dominated_by"] == [base]
    assert pts[cand]["dominance_supported"] == (pts[cand]["ci_high"] < pts[base]["ci_low"])
    assert pts[cand]["dominance_supported"] is True
    bad = await client.get("/v1/migrations/pareto", params={"run_ids": base})
    assert bad.status_code == 422
    bad = await client.get(
        "/v1/migrations/pareto", params={"run_ids": f"{base},{cand}", "metrics": "nope"}
    )
    assert bad.status_code == 422
    lat = await client.get(
        "/v1/migrations/pareto",
        params={"run_ids": f"{base},{cand}", "metrics": "pass_rate,cost,latency_p95"},
    )
    assert lat.status_code == 200 and lat.json()["metrics"][-1] == "latency_p95"


def test_new_hard_fail_scenarios_only_counts_scenarios_without_a_baseline_hard_fail():
    from types import SimpleNamespace as NS

    from gauntlet_server.services.migration import _new_hard_fail_scenarios

    def data(records, hard):
        return NS(
            records=[NS(episode_id=e, scenario_id=s) for e, s in records],
            report=NS(hard_fail_episodes=hard),
        )

    base = data([("b1", "s1"), ("b2", "s2")], ["b1"])
    cand = data([("c1", "s1"), ("c2", "s2"), ("c3", "s3")], ["c1", "c2"])
    assert _new_hard_fail_scenarios(base, cand) == ["s2"]
    assert _new_hard_fail_scenarios(base, data([("c1", "s1")], [])) == []
