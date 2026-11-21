"""Adaptive sampling on the server: creation, the advisory-locked step, caps, the report."""

from __future__ import annotations

import asyncio

import pytest
from api_helpers import drain
from gauntlet_core.eval import RunReport
from gauntlet_server.services.adaptive import adaptive_step
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def episodes_of(sm, run_id: str, scenario_id: str) -> list[tuple[int, str, str | None]]:
    async with sm() as s:
        rows = await s.execute(
            text(
                "SELECT rep, status, outcome FROM episodes WHERE run_id = :r "
                "AND scenario_id = :s ORDER BY rep"
            ),
            {"r": run_id, "s": scenario_id},
        )
        return [tuple(r) for r in rows]  # type: ignore[misc]


async def finish(sm, run_id: str, scenario_id: str, outcomes: list[str]) -> None:
    async with sm() as s, s.begin():
        for rep, outcome in enumerate(outcomes):
            await s.execute(
                text(
                    "UPDATE episodes SET status = 'done', outcome = :o WHERE run_id = :r "
                    "AND scenario_id = :s AND rep = :p"
                ),
                {"o": outcome, "r": run_id, "s": scenario_id, "p": rep},
            )


async def start(client, seed, reps: int = 6) -> str:
    r = await client.post(
        "/v1/runs",
        json={"suite_id": seed["suite_id"], "agent_version_id": seed["agent_version_id"],
              "budget_usd_micros": 2_000_000, "seed": 3, "repetitions": reps, "adaptive": True},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    assert r.json()["adaptive"] is True
    return r.json()["id"]


async def test_adaptive_run_starts_with_three_reps_per_scenario(client, sm):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    run_id = await start(client, seed)
    assert (await client.get(f"/v1/runs/{run_id}")).json()["counts"]["total"] == 30
    assert [e[0] for e in await episodes_of(sm, run_id, "scn_ecom_01")] == [0, 1, 2]
    dry = await client.post(
        "/v1/runs",
        params={"dry_run": True},
        json={"suite_id": seed["suite_id"], "agent_version_id": seed["agent_version_id"],
              "budget_usd_micros": 2_000_000, "repetitions": 6, "adaptive": True},
    )  # fmt: skip
    fixed = await client.post(
        "/v1/runs",
        params={"dry_run": True},
        json={"suite_id": seed["suite_id"], "agent_version_id": seed["agent_version_id"],
              "budget_usd_micros": 2_000_000, "repetitions": 6},
    )  # fmt: skip
    est, full = dry.json()["estimate_usd_micros"], fixed.json()["estimate_usd_micros"]
    assert est["low"] < est["expected"] < est["high"] == full["high"]
    assert est["expected"] == round(0.6 * full["expected"])


async def test_step_continues_a_mixed_scenario_and_waits_while_one_is_in_flight(client, sm):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    run_id = await start(client, seed)
    await finish(sm, run_id, "scn_ecom_01", ["passed", "failed", "passed"])
    async with sm() as s, s.begin():
        assert await adaptive_step(s, run_id, "scn_ecom_01") == "enqueued"
    eps = await episodes_of(sm, run_id, "scn_ecom_01")
    assert [e[0] for e in eps] == [0, 1, 2, 3] and eps[3][1] == "queued"
    async with sm() as s, s.begin():  # rep 3 is still queued: nothing more is added
        assert await adaptive_step(s, run_id, "scn_ecom_01") == "waiting"
    assert len(await episodes_of(sm, run_id, "scn_ecom_01")) == 4


async def test_clear_failure_stops_after_four_and_the_maximum_stops_a_mixed_one(client, sm):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    run_id = await start(client, seed, reps=5)
    await finish(sm, run_id, "scn_ecom_07", ["failed"] * 3)
    async with sm() as s, s.begin():
        assert await adaptive_step(s, run_id, "scn_ecom_07") == "enqueued"  # 0/3: not yet clear
    await finish(sm, run_id, "scn_ecom_07", ["failed"] * 4)
    async with sm() as s, s.begin():
        assert await adaptive_step(s, run_id, "scn_ecom_07") == "stopped"  # 0/4: clear
    assert len(await episodes_of(sm, run_id, "scn_ecom_07")) == 4
    await finish(sm, run_id, "scn_ecom_02", ["passed", "failed", "passed"])
    for _ in range(2):
        async with sm() as s, s.begin():
            assert await adaptive_step(s, run_id, "scn_ecom_02") == "enqueued"
        n = len(await episodes_of(sm, run_id, "scn_ecom_02"))
        await finish(
            sm, run_id, "scn_ecom_02", ["passed", "failed", "passed", "failed", "passed"][:n]
        )
    async with sm() as s, s.begin():
        assert await adaptive_step(s, run_id, "scn_ecom_02") == "stopped"  # five trials: maximum


async def test_simulator_errors_are_not_trials_but_respect_the_cap(client, sm):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    run_id = await start(client, seed, reps=3)
    await finish(sm, run_id, "scn_ecom_03", ["simulator_error"] * 3)
    for expected_total, verdict in ((4, "enqueued"), (5, "enqueued")):
        async with sm() as s, s.begin():
            assert await adaptive_step(s, run_id, "scn_ecom_03") == verdict
        assert len(await episodes_of(sm, run_id, "scn_ecom_03")) == expected_total
        await finish(sm, run_id, "scn_ecom_03", ["simulator_error"] * expected_total)
    async with sm() as s, s.begin():
        assert await adaptive_step(s, run_id, "scn_ecom_03") == "stopped"  # 3 + 2 episodes
    assert len(await episodes_of(sm, run_id, "scn_ecom_03")) == 5


async def test_two_concurrent_finishes_enqueue_one_extra_rep(client, sm):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    run_id = await start(client, seed)
    await finish(sm, run_id, "scn_ecom_04", ["passed", "failed", "passed"])

    async def step() -> str:
        async with sm() as s, s.begin():
            return await adaptive_step(s, run_id, "scn_ecom_04")

    results = await asyncio.gather(*(step() for _ in range(4)))
    assert sorted(results) == ["enqueued", "waiting", "waiting", "waiting"]
    assert len(await episodes_of(sm, run_id, "scn_ecom_04")) == 4


async def test_adaptive_run_end_to_end_uses_fewer_episodes_and_flags_the_report(client, state, sm):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    run_id = await start(client, seed, reps=5)
    await drain(state, run_id)
    run = (await client.get(f"/v1/runs/{run_id}")).json()
    assert run["status"] == "done"
    assert run["counts"]["total"] == 9 * 5 + 4  # scn_ecom_07 fails clearly and stops at four
    rep = RunReport.model_validate((await client.get(f"/v1/runs/{run_id}/report")).json())
    assert rep.caution.adaptive_sampling
    by = {s.scenario_id: s for s in rep.per_scenario}
    assert by["scn_ecom_07"].counted == 4 and by["scn_ecom_07"].posterior_mean is not None
    assert by["scn_ecom_01"].counted == 5 and by["scn_ecom_01"].posterior_mean is None
    assert [p.k for p in rep.reliability] == [1, 2, 3, 4, 5]
