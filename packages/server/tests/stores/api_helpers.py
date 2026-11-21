"""Helpers shared by the API tests that need finished runs."""

from __future__ import annotations

import asyncio

from gauntlet_server.worker import Worker
from sqlalchemy import text


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
