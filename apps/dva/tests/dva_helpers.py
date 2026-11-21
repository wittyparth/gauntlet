"""Test harness: serve the DVA (scripted brain) and a LocalFacade in-process and run a pack
scenario against them with a scripted user. No LLM is called."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any

import httpx
import uvicorn
import yaml
from dva.app import create_app
from dva.config import Settings
from gauntlet_core.engine import EpisodeCtx, MemoryJournalStore, run_episode
from gauntlet_core.packs import Pack, load_pack
from gauntlet_core.runner import make_finalizer
from gauntlet_core.schema import OpenAICompatTargetConfig
from gauntlet_core.sim import ScriptedUserSimulator
from gauntlet_core.targets import LocalFacade, OpenAICompatTarget, UrlPolicy
from gauntlet_core.world import World, build_world

REPO = Path(__file__).parents[3]
SIM_SCRIPTS = Path(__file__).parent / "fixtures" / "sim_scripts"
_PACK: Pack | None = None


def pack() -> Pack:
    global _PACK
    if _PACK is None:
        _PACK = load_pack(REPO / "packs" / "ecommerce")
    return _PACK


def load_script(scenario_id: str) -> dict[str, Any]:
    return yaml.safe_load((SIM_SCRIPTS / f"{scenario_id}.yaml").read_text())


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextmanager
def serve_dva_thread(flaws: Callable[[], set[str]], mock_base: str = "") -> Iterator[str]:
    """The DVA in a background thread (for the synchronous CLI). Yields its base URL."""
    port = free_port()
    app = create_app(flaws, Settings(brain="scripted", mock_base=mock_base or "http://127.0.0.1:1"))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@asynccontextmanager
async def serving(flaws: set[str], scripted: Any = None):  # type: ignore[no-untyped-def]
    """Yield `(dva_base_url, facade)` with both servers started on ephemeral ports.
    `scripted` selects another scripted brain (the SQL or email agent)."""
    import asyncio

    app = create_app(lambda: flaws, Settings(brain="scripted"), scripted=scripted)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="off")
    )
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    facade = LocalFacade(secret=b"k" * 32)
    await facade.start()
    try:
        yield f"http://127.0.0.1:{port}", facade
    finally:
        await facade.stop()
        server.should_exit = True
        await task


async def run_scenario(
    scenario_id: str, turns: list[str], dva_url: str, facade: LocalFacade
) -> tuple[str, list[str], list[str]]:
    """Returns (outcome, failing check ids, agent replies)."""
    p = pack()
    scn = p.scenarios[scenario_id]
    built = build_world(p.world, scn.world_overrides, 7)
    store = MemoryJournalStore()
    ctx = await EpisodeCtx.open(store, f"ep_{scenario_id}", run_id="run_1", rng_seed=7)
    ctx.clock_start = p.world.clock_start  # the runner does not set it yet (reported gap)
    World(built).bind(ctx)
    cfg = OpenAICompatTargetConfig(base_url=f"{dva_url}/v1", model="dva", wired=True)
    async with httpx.AsyncClient() as http:
        target = OpenAICompatTarget(
            cfg,
            secrets={},
            client=http,
            safety=UrlPolicy(allow_private=True),
            facade=facade,
        )
        result = await run_episode(
            ctx,
            scn,
            target,
            ScriptedUserSimulator(turns),
            finalize=make_finalizer(scn, built, judge_enabled=False),
        )
    events = (await store.load(ctx.episode_id)).events
    failing = [
        e.payload["check_id"]
        for e in events
        if e.kind == "check_result" and e.payload["holds"] != (e.payload["check_id"] == "success")
    ]
    replies = [e.payload["text"] for e in events if e.kind == "agent_message"]
    return result.outcome, failing, replies


async def run_wired(
    agent: str, flaws: set[str], variant: str, text: str
) -> tuple[list[Any], list[str]]:
    """One benign-style turn against the SQL or email DVA in the given world variant.
    Returns (journal events, agent replies)."""
    from dva.config import world_file
    from dva.email_agent import brain_scripted as email_brain
    from dva.sql_agent import brain_scripted as sql_brain
    from gauntlet_core.schema import Scenario, WorldSpec, load_yaml

    brain = {"sql": sql_brain, "email": email_brain}[agent].respond
    world = load_yaml(WorldSpec, world_file(agent, variant))
    scn = Scenario.model_validate(
        {
            "id": f"scn_{agent}_probe", "title": "probe", "goal": text,
            "persona": "per_cooperative",
            "world": world, "opening_message": text, "max_turns": 2, "tags": {"placed": "true"},
            "success": {"type": "output", "matcher": {"regex": ".*"}},
        }
    )  # fmt: skip
    built = build_world(world, None, 7)
    store = MemoryJournalStore()
    ctx = await EpisodeCtx.open(store, "ep_probe", run_id="run_1", rng_seed=7)
    ctx.clock_start = world.clock_start
    World(built).bind(ctx)
    async with serving(flaws, brain) as (url, facade):
        cfg = OpenAICompatTargetConfig(base_url=f"{url}/v1", model="dva", wired=True)
        async with httpx.AsyncClient() as http:
            target = OpenAICompatTarget(
                cfg, secrets={}, client=http, safety=UrlPolicy(allow_private=True), facade=facade
            )
            await run_episode(
                ctx, scn, target, ScriptedUserSimulator([text]),
                finalize=make_finalizer(scn, built, judge_enabled=False),
            )  # fmt: skip
    events = (await store.load("ep_probe")).events
    return events, [e.payload["text"] for e in events if e.kind == "agent_message"]
