"""Cron table, exactly-once ticks, budget skips, disabled schedules, audited run-now."""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import UTC, datetime, timedelta

import pytest
from gauntlet_server.services.schedules import CronError, next_fire, tick
from sqlalchemy import text

T = datetime(2026, 3, 4, 10, 30, tzinfo=UTC)  # a Wednesday


@pytest.mark.parametrize(
    ("expr", "after", "expected"),
    [
        ("* * * * *", T, T + timedelta(minutes=1)),
        ("*/15 * * * *", T, datetime(2026, 3, 4, 10, 45, tzinfo=UTC)),
        ("0 12 * * *", T, datetime(2026, 3, 4, 12, 0, tzinfo=UTC)),
        ("0 9 * * *", T, datetime(2026, 3, 5, 9, 0, tzinfo=UTC)),
        ("30 10 * * *", T, datetime(2026, 3, 5, 10, 30, tzinfo=UTC)),  # strictly after
        ("0 0 1 * *", T, datetime(2026, 4, 1, 0, 0, tzinfo=UTC)),
        ("0 8 * * 1", T, datetime(2026, 3, 9, 8, 0, tzinfo=UTC)),  # next Monday
        ("0 8 * * 7", T, datetime(2026, 3, 8, 8, 0, tzinfo=UTC)),  # 7 is Sunday
        ("5,35 10-11 * * *", T, datetime(2026, 3, 4, 10, 35, tzinfo=UTC)),
        ("0 0 13 * 5", T, datetime(2026, 3, 6, 0, 0, tzinfo=UTC)),  # day OR weekday: Friday
        ("0 0 29 2 *", T, datetime(2028, 2, 29, 0, 0, tzinfo=UTC)),
    ],
)
def test_cron_table(expr, after, expected):
    assert next_fire(expr, after) == expected


@pytest.mark.parametrize(
    "bad", ["", "* * * *", "60 * * * *", "* 24 * * *", "*/0 * * * *", "a * * * *", "0 0 31 2 *"]
)
def test_bad_cron(bad):
    with pytest.raises(CronError):
        next_fire(bad, T)


async def make(client, **kw):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    body = {
        "agent_version_id": seed["agent_version_id"],
        "suite_id": seed["suite_id"],
        "cron": "*/5 * * * *",
        "budget_usd_micros": 1_000_000,
        **kw,
    }
    r = await client.post("/v1/schedules", json=body)
    assert r.status_code == 201, r.text
    return seed, r.json()


async def run_count(sm, suite_id: str) -> int:
    async with sm() as s:
        return (
            await s.execute(text("SELECT count(*) FROM runs WHERE suite_id = :s"), {"s": suite_id})
        ).scalar_one()


@pytest.mark.integration
async def test_crud_and_validation(client):
    seed, sch = await make(client)
    assert sch["timezone"] == "UTC" and sch["enabled"] and sch["next_fire_at"]
    assert len((await client.get("/v1/schedules")).json()) == 1
    p = await client.patch(
        f"/v1/schedules/{sch['id']}", json={"cron": "0 * * * *", "enabled": False}
    )
    assert p.json()["next_fire_at"] is None and p.json()["cron"] == "0 * * * *"
    base = {
        "agent_version_id": seed["agent_version_id"],
        "suite_id": seed["suite_id"],
        "budget_usd_micros": 1,
    }
    assert (await client.post("/v1/schedules", json={**base, "cron": "nope"})).status_code == 422
    assert (
        await client.post(
            "/v1/schedules", json={**base, "cron": "* * * * *", "timezone": "Europe/Paris"}
        )
    ).status_code == 422
    assert (await client.delete(f"/v1/schedules/{sch['id']}")).status_code == 204


@pytest.mark.integration
async def test_no_schedule_means_no_fire(state, sm, client):
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    before = await run_count(sm, seed["suite_id"])
    assert await tick(state, T + timedelta(days=1)) == []
    assert await run_count(sm, seed["suite_id"]) == before


@pytest.mark.integration
async def test_two_racing_ticks_fire_once(state, sm, client):
    seed, _sch = await make(client)
    before = await run_count(sm, seed["suite_id"])
    later = datetime.now(UTC) + timedelta(hours=1)
    a, b = await asyncio.gather(tick(state, later), tick(state, later))
    assert len(a) + len(b) == 1
    assert await run_count(sm, seed["suite_id"]) == before + 1
    row = (await client.get("/v1/schedules")).json()[0]
    assert row["last_status"] == "fired" and row["last_run_id"]
    assert datetime.fromisoformat(row["next_fire_at"]) > later  # moved past the tick
    assert await tick(state, later) == []  # not due again


@pytest.mark.integration
async def test_disabled_schedule_never_fires(state, sm, client):
    seed, _sch = await make(client, enabled=False)
    before = await run_count(sm, seed["suite_id"])
    assert await tick(state, datetime.now(UTC) + timedelta(days=2)) == []
    assert await run_count(sm, seed["suite_id"]) == before


@pytest.mark.integration
async def test_budget_skip_is_recorded(state, sm, client):
    seed, _sch = await make(client)
    state.settings = dataclasses.replace(state.settings, daily_budget_usd_micros=1)
    before = await run_count(sm, seed["suite_id"])
    out = await tick(state, datetime.now(UTC) + timedelta(hours=1))
    assert [o.status for o in out] == ["skipped_budget"]
    assert await run_count(sm, seed["suite_id"]) == before
    row = (await client.get("/v1/schedules")).json()[0]
    assert row["skipped_budget"] == 1 and row["last_status"] == "skipped_budget"


@pytest.mark.integration
async def test_run_now_is_audited_and_keeps_next_fire(client, sm):
    _seed, sch = await make(client)
    r = await client.post(f"/v1/schedules/{sch['id']}/run-now")
    assert r.status_code == 200 and r.json()["status"] == "fired" and r.json()["run_id"]
    after = (await client.get("/v1/schedules")).json()[0]
    assert after["next_fire_at"] == sch["next_fire_at"]
    async with sm() as s:
        acts = (
            (
                await s.execute(
                    text("SELECT action FROM audit_log WHERE subject_id = :i"), {"i": sch["id"]}
                )
            )
            .scalars()
            .all()
        )
    assert "schedule.run_now" in acts and "schedule.create" in acts
    assert (await client.post("/v1/schedules/sch_nope/run-now")).status_code == 404
