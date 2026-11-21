"""Baselines, run comparison and trajectory diff over the seeded demo suite."""

from __future__ import annotations

import asyncio

import pytest
from gauntlet_core.eval import CompareReport, TrajectoryDiff
from gauntlet_server.worker import Worker
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def drain(state, run_id: str) -> None:
    stop = asyncio.Event()
    task = asyncio.create_task(Worker(state, concurrency=2).run(stop))
    try:
        for _ in range(600):
            async with state.sm() as s:
                status = (
                    await s.execute(text("SELECT status FROM runs WHERE id = :r"), {"r": run_id})
                ).scalar()
            if status in ("done", "cancelled", "failed"):
                return
            await asyncio.sleep(0.1)
        raise AssertionError("run did not finish")
    finally:
        stop.set()
        await task


async def new_run(client, state, seed: dict, *, wait: bool = True, **extra) -> str:
    r = await client.post(
        "/v1/runs",
        json={
            "suite_id": seed["suite_id"],
            "agent_version_id": seed["agent_version_id"],
            "budget_usd_micros": 2_000_000,
            "seed": 7,
            **extra,
        },
    )
    assert r.status_code == 201, r.text
    run_id = r.json()["id"]
    if wait:
        await drain(state, run_id)
    return run_id


@pytest.fixture
async def two_runs(client, state):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    return seed, seed["run_id"], await new_run(client, state, seed)


async def test_compare_two_identical_runs_and_default_baseline(client, state, two_runs):
    _, base, cand = two_runs
    assert (await client.get(f"/v1/runs/{cand}/compare")).status_code == 404  # no baseline yet
    r = await client.put(f"/v1/runs/{cand}/baseline", json={"baseline_run_id": base})
    assert r.status_code == 200 and r.json()["baseline_of"] == base
    got = await client.get(f"/v1/runs/{cand}/compare")
    rep = CompareReport.model_validate(got.json())
    assert rep.baseline_id == base and rep.run_id == cand and rep.shared_scenarios == 10
    assert rep.verdict == "no_detectable_change" and rep.delta == 0
    explicit = await client.get(f"/v1/runs/{cand}/compare", params={"baseline": base})
    assert explicit.json() == got.json()  # deterministic
    assert (await client.delete(f"/v1/runs/{cand}/baseline")).json()["baseline_of"] is None
    assert (await client.get(f"/v1/runs/{cand}/compare")).status_code == 404


async def test_flip_and_trajectory_diff_to_the_hand_checked_divergence(client, state, two_runs, sm):
    seed, base, cand = two_runs
    # the candidate breaks scn_ecom_03: mark its episode failed (the baseline passed it)
    async with sm() as s, s.begin():
        await s.execute(
            text("UPDATE episodes SET outcome = 'failed' WHERE run_id = :r AND scenario_id = :s"),
            {"r": cand, "s": "scn_ecom_03"},
        )
    rep = CompareReport.model_validate(
        (await client.get(f"/v1/runs/{cand}/compare", params={"baseline": base})).json()
    )
    flip = next(f for f in rep.flips if f.scenario_id == "scn_ecom_03")
    assert flip.status == "newly_failing" and flip.single_trial
    assert flip.episode_baseline and flip.episode_run
    d = await client.get(
        f"/v1/episodes/{flip.episode_run}/diff", params={"against": flip.episode_baseline}
    )
    diff = TrajectoryDiff.model_validate(d.json())
    # the two runs executed the same scripted conversation: nothing diverges
    assert diff.first_divergence is None and not diff.truncated
    # hand-checked divergence: rewrite the candidate's first agent reply
    detail = (await client.get(f"/v1/episodes/{flip.episode_run}")).json()
    agent_seqs = [e["seq"] for e in detail["events"] if e["kind"] == "agent_message"]
    async with sm() as s, s.begin():
        await s.execute(
            text(
                "UPDATE events SET doc = jsonb_set(doc, '{payload,text}', "
                "'\"zzz qqq entirely different\"') WHERE episode_id = :e AND seq = :q"
            ),
            {"e": flip.episode_run, "q": agent_seqs[0]},
        )
    d = await client.get(
        f"/v1/episodes/{flip.episode_run}/diff", params={"against": flip.episode_baseline}
    )
    moved = TrajectoryDiff.model_validate(d.json())
    assert agent_seqs[0] in moved.first_divergence  # the rewritten reply no longer aligns
    # against the demo's failing episode of another scenario the first step already differs
    other = await client.get(
        f"/v1/episodes/{seed['failed_episode_id']}/diff", params={"against": flip.episode_run}
    )
    od = TrajectoryDiff.model_validate(other.json())
    assert od.first_divergence is not None
    first = next(r for r in od.rows if r.status != "same")
    assert (first.a_seq, first.b_seq) == od.first_divergence


async def test_baseline_validation(client, state, two_runs, sm):
    seed, base, cand = two_runs
    queued = await new_run(client, state, seed, wait=False)
    r = await client.put(f"/v1/runs/{queued}/baseline", json={"baseline_run_id": base})
    assert r.status_code == 409 and r.json()["error"]["code"] == "run_not_completed"
    r = await client.put(f"/v1/runs/{cand}/baseline", json={"baseline_run_id": queued})
    assert r.status_code == 409
    r = await client.put(f"/v1/runs/{cand}/baseline", json={"baseline_run_id": cand})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_baseline"
    r = await client.put(f"/v1/runs/{cand}/baseline", json={"baseline_run_id": "run_nope"})
    assert r.status_code == 404
    async with sm() as s, s.begin():  # another suite
        await s.execute(
            text("INSERT INTO suites (id, workspace_id, name) VALUES ('other', 'ws_test', 'o')")
        )
        await s.execute(text("UPDATE runs SET suite_id = 'other' WHERE id = :r"), {"r": base})
    r = await client.put(f"/v1/runs/{cand}/baseline", json={"baseline_run_id": base})
    assert r.status_code == 422 and r.json()["error"]["code"] == "suite_mismatch"


async def test_run_created_with_baseline_and_cross_workspace_404(client, state, two_runs, sm):
    seed, base, _ = two_runs
    rid = await new_run(client, state, seed, wait=False, baseline_run_id=base)
    assert (await client.get(f"/v1/runs/{rid}")).json()["baseline_of"] == base
    bad = await client.post(
        "/v1/runs",
        json={"suite_id": seed["suite_id"], "agent_version_id": seed["agent_version_id"],
              "budget_usd_micros": 1_000_000, "baseline_run_id": "run_nope"},
    )  # fmt: skip
    assert bad.status_code == 404
    async with sm() as s, s.begin():
        await s.execute(text("INSERT INTO workspaces (id, name) VALUES ('ws_other', 'o')"))
        await s.execute(
            text("UPDATE runs SET workspace_id = 'ws_other' WHERE id = :r"), {"r": base}
        )
        await s.execute(
            text("UPDATE episodes SET workspace_id = 'ws_other' WHERE run_id = :r"), {"r": base}
        )
    ep = (await client.get(f"/v1/runs/{rid}/episodes")).json()["items"][0]["id"]
    assert (
        await client.get(f"/v1/episodes/{ep}/diff", params={"against": "ep_demo_0"})
    ).status_code == 404
    assert (
        await client.get(f"/v1/runs/{rid}/compare", params={"baseline": base})
    ).status_code == 404
