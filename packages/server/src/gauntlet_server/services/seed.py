"""`POST /v1/dev/seed`: idempotent data from the ecommerce pack plus one finished run executed
through the real runner and worker code with a scripted model (no network). Dev mode only.

The pack (`packs/ecommerce`, or `GAUNTLET_PACK_DIR`) provides the world, 30 approved scenarios and
its suites. The run covers the 10-scenario smoke suite: nine pass; `scn_ecom_07` fails (a refund
outside the window, with a world patch and a judge verdict whose evidence quote is present in
the cited event). One extra scenario is stored as a `draft`."""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from typing import Any

from gauntlet_core.eval import load_rubrics
from gauntlet_core.llm import ScriptedLLM
from gauntlet_core.packs import Pack, load_pack
from gauntlet_core.schema import Scenario
from gauntlet_core.sim import load_persona_library
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import models as m
from ..deps import AppState
from ..worker import Worker
from .runs import RunCreate, create_run
from .seed_gateway import POLICY, seed_gateway
from .seed_script import MODEL, build_script

__all__ = ["script", "seed_demo"]

PROJECT, AGENT, VERSION = "proj_demo", "agt_demo", "agv_demo"
WORLD, RUN = "ecommerce", "run_demo"
RUN_B = "run_demo_b"  # a second finished scripted run of the suite: the compare view's fixture
SUITE, SUITE_FULL = "ecommerce_smoke", "ecommerce_full"
PASS_N = 9  # smoke episodes that pass; one more fails
EPISODES = [f"ep_demo_{i}" for i in range(PASS_N + 1)]
EPISODES_B = [f"ep_demo_b_{i}" for i in range(PASS_N + 1)]


def resolve_pack_dir(
    env: Mapping[str, str] | None = None, here: Path | None = None, cwd: Path | None = None
) -> Path:
    """`GAUNTLET_PACK_DIR`, else the first existing `packs/ecommerce` among: next to the source
    tree (checkout), under the working directory, and `/app` (the container image, where the
    package is installed into site-packages and the source-relative path is meaningless)."""
    given = (os.environ if env is None else env).get("GAUNTLET_PACK_DIR")
    if given:
        return Path(given)
    here = here or Path(__file__).resolve()
    candidates = [
        here.parents[5] / "packs" / "ecommerce",
        (cwd or Path.cwd()) / "packs" / "ecommerce",
        Path("/app/packs/ecommerce"),
    ]
    for c in candidates:
        if (c / "pack.yaml").is_file():
            return c
    raise FileNotFoundError(
        "packs/ecommerce not found (set GAUNTLET_PACK_DIR); looked in "
        + ", ".join(str(c) for c in candidates)
    )


@cache
def pack() -> Pack:
    return load_pack(resolve_pack_dir())


def script() -> dict[str, Any]:
    return build_script(pack())


def _draft_scenario() -> dict[str, Any]:
    return {
        "id": "scn_draft_status",
        "title": "Draft: order status in a hurry",
        "goal": "find out where order ord_1004 is, quickly",
        "persona": "per_impatient",
        "hidden_facts": ["Order id is ord_1004."],
        "world": WORLD,
        "max_turns": 4,
        "success": {"type": "tool_called", "tool": "lookup_order"},
    }


async def _reset(s: AsyncSession) -> None:
    for sql in (
        "DELETE FROM verdicts WHERE episode_id LIKE 'ep_demo_%'",
        "DELETE FROM events_archive WHERE episode_id LIKE 'ep_demo_%'",
        "DELETE FROM effects_archive WHERE episode_id LIKE 'ep_demo_%'",
        "DELETE FROM events WHERE episode_id LIKE 'ep_demo_%'",
        "DELETE FROM effects WHERE episode_id LIKE 'ep_demo_%'",
        "DELETE FROM episodes WHERE run_id IN ('run_demo', 'run_demo_b')",
        "DELETE FROM runs WHERE id IN ('run_demo', 'run_demo_b')",
        "DELETE FROM gateway_approvals WHERE id = 'gap_demo'",
        "DELETE FROM gateway_decisions WHERE id LIKE 'gdc_demo_%'",
        "DELETE FROM findings WHERE id = 'fnd_demo_policy'",
        "DELETE FROM policy_tests WHERE id = 'ptt_demo'",
        "DELETE FROM policy_proposals WHERE policy_id = 'pol_demo'",
        "DELETE FROM policies WHERE id = 'pol_demo'",
    ):
        await s.execute(text(sql))


async def _drop_legacy_demo(s: AsyncSession) -> None:
    """Remove what the pre-pack seed created, so a dev database does not keep a second,
    stale demo (its suite, scenarios and the agent version they were run with)."""
    for sql in (
        "DELETE FROM suite_scenarios WHERE suite_id = 'suite_demo_smoke'",
        "DELETE FROM suites WHERE id = 'suite_demo_smoke' "
        "AND NOT EXISTS (SELECT 1 FROM runs WHERE suite_id = 'suite_demo_smoke')",
        "DELETE FROM scenarios WHERE id LIKE 'demo\\_%' "
        "AND NOT EXISTS (SELECT 1 FROM episodes WHERE scenario_id = scenarios.id)",
        "DELETE FROM agent_versions WHERE id = :v "
        "AND NOT EXISTS (SELECT 1 FROM runs WHERE agent_version_id = :v)",
    ):
        await s.execute(text(sql), {"v": VERSION})


async def _upsert_docs(s: AsyncSession, ws: str) -> None:
    p = pack()
    if await s.get(m.Project, PROJECT) is None:
        s.add(m.Project(id=PROJECT, workspace_id=ws, name="Demo"))
        await s.flush()
    if await s.get(m.Agent, AGENT) is None:
        s.add(m.Agent(id=AGENT, workspace_id=ws, project_id=PROJECT, name="Demo support agent"))
        await s.flush()
    config = {
        "target": {
            "kind": "hosted",
            "model": MODEL,
            "system_prompt": "You are the support assistant of an outdoor gear store. "
            "Follow the store policy.\n\n" + p.policy_text,
        },
        "profile": {
            "purpose": "Customer support for an online outdoor gear store",
            "policies_text": p.policy_text,
        },
    }
    version = await s.get(m.AgentVersion, VERSION)
    if version is None:
        s.add(
            m.AgentVersion(
                id=VERSION,
                workspace_id=ws,
                agent_id=AGENT,
                label="v1",
                world_id=WORLD,
                config=config,
            )
        )
    elif version.config != config:  # the seed owns this version: keep it current
        version.config = config
    if await s.get(m.World, (WORLD, 1)) is None:
        s.add(
            m.World(
                id=WORLD,
                version=1,
                workspace_id=ws,
                doc=p.world.model_dump(mode="json", exclude_none=True),
            )
        )
    for pid, persona in load_persona_library().items():
        if await s.get(m.Persona, (pid, 1)) is None:
            s.add(
                m.Persona(
                    id=pid,
                    version=1,
                    workspace_id=ws,
                    doc=persona.model_dump(mode="json", exclude_none=True),
                )
            )
    for rid, rubric in load_rubrics().items():
        if await s.get(m.Rubric, (rid, rubric.version)) is None:
            s.add(
                m.Rubric(
                    id=rid,
                    version=rubric.version,
                    workspace_id=ws,
                    doc=rubric.model_dump(mode="json", exclude_none=True),
                )
            )
    rows = [(d, "approved", "pack") for d in p.scenarios.values()]
    rows.append((Scenario.model_validate(_draft_scenario()), "draft", "generated"))
    for scn, status, source in rows:
        if await s.get(m.Scenario, (scn.id, 1)) is None:
            s.add(
                m.Scenario(
                    id=scn.id,
                    version=1,
                    workspace_id=ws,
                    doc=scn.model_dump(mode="json", exclude_none=True),
                    status=status,
                    source=source,
                )
            )
    await s.flush()
    for suite_id, pack_suite in ((SUITE, "smoke"), (SUITE_FULL, "full")):
        if await s.get(m.Suite, suite_id) is None:
            suite = p.suites[pack_suite]
            s.add(m.Suite(id=suite_id, workspace_id=ws, name=suite.name, repetitions=1))
            await s.flush()
            for pos, scn_id in enumerate(suite.scenarios):
                s.add(m.SuiteScenario(suite_id=suite_id, scenario_id=scn_id, position=pos))
    await s.flush()


async def seed_demo(
    state: AppState,
    ws: str,
    *,
    reset: bool = False,
    compare_run: bool = False,
    gateway: bool = False,
) -> dict[str, Any]:
    async with state.sm() as s, s.begin():
        if reset:
            await _reset(s)
        await _upsert_docs(s, ws)
    async with state.sm() as s:
        run = await s.get(m.Run, RUN)
    if run is not None and run.suite_id != SUITE:  # left by an older seed (another suite)
        async with state.sm() as s, s.begin():
            await _reset(s)
            await _drop_legacy_demo(s)
            await _upsert_docs(s, ws)
        run = None
    if run is None:
        async with state.sm() as s, s.begin():
            await create_run(
                s,
                state,
                ws,
                RunCreate(
                    suite_id=SUITE,
                    agent_version_id=VERSION,
                    budget_usd_micros=5_000_000,
                    seed=1,
                ),
                run_id=RUN,
                episode_ids=EPISODES,
                enforce_daily=False,
            )
            leases = await _lease_own(s, RUN)  # same transaction: no worker can claim them
        await _execute(state, leases)
    async with state.sm() as s:
        run_b = await s.get(m.Run, RUN_B)
    if compare_run and run_b is None:
        async with state.sm() as s, s.begin():
            await create_run(
                s,
                state,
                ws,
                RunCreate(
                    suite_id=SUITE,
                    agent_version_id=VERSION,
                    budget_usd_micros=5_000_000,
                    seed=1,
                ),
                run_id=RUN_B,
                episode_ids=EPISODES_B,
                enforce_daily=False,
            )
            leases = await _lease_own(s, RUN_B)  # same transaction: no worker can claim them
        await _execute(state, leases)
    if gateway:
        async with state.sm() as s, s.begin():
            await seed_gateway(s, ws, AGENT, VERSION)
    async with state.sm() as s:
        failed = (
            (
                await s.execute(
                    select(m.Episode.id).where(
                        m.Episode.run_id == RUN, m.Episode.outcome == "failed"
                    )
                )
            )
            .scalars()
            .first()
        )
    return {
        "api_key_hint": state.settings.dev_api_key[:8] or None,
        "project_id": PROJECT,
        "agent_id": AGENT,
        "agent_version_id": VERSION,
        "suite_id": SUITE,
        "run_id": RUN,
        "policy_id": POLICY if gateway else None,
        "compare_run_id": RUN_B if compare_run or run_b is not None else None,
        "failed_episode_id": failed,
    }


async def _lease_own(s: AsyncSession, run_id: str) -> list[Any]:
    """Lease a demo run's queued episodes to the seed itself. Called in the transaction that
    creates the run, so a live worker (real gateway) can never claim them first."""
    from gauntlet_core.engine import EpisodeLease

    rows = (
        await s.execute(
            text(
                "UPDATE episodes SET status = 'leased', lease_owner = 'seed', "
                "epoch = epoch + 1, started_at = now(), "
                "lease_expires_at = now() + interval '300 seconds' "
                "WHERE run_id = :r AND status = 'queued' "
                "RETURNING id, run_id, epoch, attempt"
            ),
            {"r": run_id},
        )
    ).all()
    await s.execute(text("UPDATE runs SET status = 'running' WHERE id = :r"), {"r": run_id})
    return [EpisodeLease(r.id, r.run_id, r.epoch, "seed", 300, r.attempt) for r in rows]


async def _execute(state: AppState, leases: list[Any]) -> None:
    """Run a demo run's leased episodes through the worker code with the scripted model."""
    scripted = dataclasses.replace(state, gateway=ScriptedLLM(script()))
    worker = Worker(scripted, worker_id="seed", lease_s=300)
    await worker.run_leases(leases)
