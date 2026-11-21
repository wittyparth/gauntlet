"""Serve the api app and the DVA (scripted brain) on ephemeral ports so a real Worker can run
campaign episodes end to end. No model is called: the simulator is a scripted gateway."""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import uvicorn
from dva.app import create_app as create_dva
from dva.config import Settings as DvaSettings
from gauntlet_core.llm import ScriptedLLM
from gauntlet_server.app import create_app
from gauntlet_server.worker import Worker

SIM_SCRIPT = {
    "roles": {
        "simulator": [
            {
                "match": "ord_1001",
                "replies": [
                    {
                        "parsed": {
                            "state_note": "n",
                            "action": "say",
                            "message": "Where is order ord_1001?",
                        }
                    },
                    {
                        "parsed": {
                            "state_note": "n",
                            "action": "done",
                            "done_reason": "goal_met",
                        }
                    },
                ],
            }
        ]
    }
}


async def _serve(app: Any) -> tuple[uvicorn.Server, asyncio.Task[None], int]:
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="off")
    )
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    return server, task, int(server.servers[0].sockets[0].getsockname()[1])


@asynccontextmanager
async def live_stack(state: Any, flaws: set[str]) -> AsyncIterator[str]:
    """Yields the DVA base URL (`.../v1`). `flaws` is read on every request, so a test can
    switch a flaw off between runs. The state's settings point the facade at the api server."""
    state.gateway = ScriptedLLM(SIM_SCRIPT)
    api, api_task, api_port = await _serve(create_app(state))
    state.settings = dataclasses.replace(
        state.settings,
        public_api_url=f"http://127.0.0.1:{api_port}",
        allow_private_targets=True,
        kill_poll_s=0.2,
    )
    dva, dva_task, dva_port = await _serve(create_dva(lambda: flaws, DvaSettings(brain="scripted")))
    try:
        yield f"http://127.0.0.1:{dva_port}/v1"
    finally:
        for server, task in ((dva, dva_task), (api, api_task)):
            server.should_exit = True
            await task


async def drain(state: Any, client: httpx.AsyncClient, run_id: str, timeout: float = 60) -> dict:
    """Run a worker until the run reaches a terminal status; returns the run."""
    worker = Worker(state, concurrency=4, poll_interval_s=0.05)
    stop = asyncio.Event()
    task = asyncio.create_task(worker.run(stop))
    run: dict = {}
    try:
        for _ in range(int(timeout / 0.1)):
            run = (await client.get(f"/v1/runs/{run_id}")).json()
            if run["status"] in ("done", "cancelled", "failed"):
                return run
            await asyncio.sleep(0.1)
        raise AssertionError(f"run {run_id} did not finish: {run}")
    finally:
        stop.set()
        await asyncio.wait_for(task, 15)


async def run_campaign(
    state: Any, client: httpx.AsyncClient, version: str, attack_ids: list[str], **extra: Any
) -> dict:
    """POST a campaign over the stored benign scenario and drain it. Returns the final run."""
    body = {
        "agent_version_id": version,
        "world_id": "ecommerce",
        "benign_scenario_ids": extra.pop("benign", ["scn_benign_status"]),
        "attack_ids": attack_ids,
        "budget_usd_micros": 5_000_000,
        **extra,
    }
    r = await client.post("/v1/campaigns", json=body)
    assert r.status_code == 201, r.text
    return await drain(state, client, r.json()["campaign_id"])
