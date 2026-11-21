"""Local-mode orchestration for `gauntlet run`: plan, execute with bounded concurrency over a
SQLite journal, aggregate. All episode logic lives in `gauntlet_core.runner`."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from gauntlet_core.engine import (
    MemoryBudgetLedger,
    NonDeterminism,
    SqliteJournalStore,
    StaleLease,
    dump_cassette,
)
from gauntlet_core.eval import EpisodeRecord, RunReport, aggregate_run, load_rubrics
from gauntlet_core.eval.stability import AdaptiveScheduler
from gauntlet_core.ids import new_id
from gauntlet_core.llm import Gateway
from gauntlet_core.packs import Pack
from gauntlet_core.runner import (
    EpisodeJob,
    EpisodeOutcome,
    RunnerDeps,
    derive_episode_seed,
    execute_with_attempts,
)
from gauntlet_core.schema import AgentProfile, AgentVersion, Scenario, Verdict
from gauntlet_core.targets import LocalFacade, UrlPolicy

from .agentfile import AgentFile
from .localdb import LocalDb

__all__ = ["RunPlan", "build_report", "collect_secrets", "execute_plan", "make_plan"]

_SECRET_REF = re.compile(r"\{\{\s*secret:([A-Za-z0-9_.-]+)\s*\}\}")


@dataclass
class RunPlan:
    run_id: str
    out: Path
    pack: Pack
    agent: AgentVersion
    scenarios: list[Scenario]
    reps: int
    seed: int
    budget_micros: int
    concurrency: int
    judge: bool
    suite_id: str
    secrets: dict[str, str] = field(default_factory=dict)
    episodes: dict[str, tuple[str, int]] = field(default_factory=dict)  # id -> (scenario, rep)
    adaptive: bool = False  # sequential stopping per scenario (P3-2)


def collect_secrets(agent: AgentFile) -> dict[str, str]:
    """Secrets are read from environment variables named like the secret."""
    cfg = agent.target
    names: set[str] = set()
    if cfg.kind == "openai_compat" and cfg.api_key_secret:
        names.add(cfg.api_key_secret)
    if cfg.kind == "http":
        for v in cfg.headers.values():
            names.update(_SECRET_REF.findall(v))
    return {n: os.environ[n] for n in names if n in os.environ}


def make_plan(
    *,
    run_id: str,
    out: Path,
    pack: Pack,
    agent: AgentFile,
    scenarios: list[Scenario],
    reps: int,
    seed: int,
    budget_micros: int,
    concurrency: int,
    judge: bool,
    suite_id: str,
    episode_ids: dict[str, tuple[str, int]],
    adaptive: bool = False,
) -> RunPlan:
    profile = agent.profile or AgentProfile(purpose=pack.title, policies_text=pack.policy_text)
    version = AgentVersion(
        id=f"agv_{run_id}",
        agent_id="local",
        label=agent.label,
        target=agent.target,
        profile=profile,
    )
    return RunPlan(
        run_id, out, pack, version, scenarios, reps, seed, budget_micros, concurrency, judge,
        suite_id, collect_secrets(agent), episode_ids, adaptive,
    )  # fmt: skip


def _job(plan: RunPlan, ep_id: str) -> EpisodeJob:
    scn_id, rep = plan.episodes[ep_id]
    scn = plan.pack.scenarios[scn_id]
    return EpisodeJob(
        episode_id=ep_id,
        run_id=plan.run_id,
        scenario=scn,
        world=plan.pack.world if isinstance(scn.world, str) else scn.world,
        agent_version=plan.agent,
        persona=plan.pack.personas[scn.persona],
        rubrics=load_rubrics(scn.rubrics),
        rng_seed=derive_episode_seed(plan.seed, scn_id, rep),
        secrets=plan.secrets,
    )


def _platform_error(detail: str) -> EpisodeOutcome:
    from gauntlet_core.schema import Cost

    return EpisodeOutcome("platform_error", "error", detail, Cost(), (), [], "full", 0)


async def execute_plan(
    plan: RunPlan,
    gateway: Gateway,
    db: LocalDb,
    *,
    on_done: Callable[[str, EpisodeOutcome], None] | None = None,
) -> None:
    """Run every episode that has no recorded outcome yet (this is also `--resume`)."""
    store = await SqliteJournalStore.open(str(plan.out / "journal.db"))
    facade: LocalFacade | None = None
    if plan.agent.target.kind != "hosted" and plan.agent.target.wired:
        facade = LocalFacade(secret=os.urandom(32))
        await facade.start()
    pending = {e.id for e in db.episodes(plan.run_id) if e.outcome is None}
    sem = asyncio.Semaphore(plan.concurrency)
    try:
        async with httpx.AsyncClient() as http:
            deps = RunnerDeps(
                store=store,
                gateway=gateway,
                budget=MemoryBudgetLedger(plan.budget_micros),
                http=http,
                url_policy=UrlPolicy(allow_private=True),
                facade=facade,
                judge_enabled=plan.judge,
            )

            scheduler = AdaptiveScheduler(plan.reps) if plan.adaptive else None
            if scheduler:  # replay what a resumed run already finished into the scheduler
                scheduler.start(sorted({s for s, _ in plan.episodes.values()}))
                for e in db.episodes(plan.run_id):
                    if e.outcome is not None:
                        scheduler.record(e.scenario_id, e.outcome)
            tasks: set[asyncio.Task[None]] = set()

            def spawn(ep_id: str) -> None:
                task = asyncio.create_task(one(ep_id))
                tasks.add(task)
                task.add_done_callback(tasks.discard)

            async def one(ep_id: str) -> None:
                async with sem:
                    epoch = await store.bump_epoch(ep_id)
                    try:
                        out = await execute_with_attempts(_job(plan, ep_id), deps, epoch=epoch)
                    except (NonDeterminism, StaleLease) as e:
                        out = _platform_error(f"{type(e).__name__}: {e}")
                    except Exception as e:  # one broken episode must not stop the run
                        out = _platform_error(f"{type(e).__name__}: {e}")
                    db.finish_episode(
                        ep_id,
                        out.outcome,
                        out.termination,
                        out.cost.usd_micros,
                        out.latency_ms,
                        out.reasons,
                        out.world_fidelity,
                    )
                    if on_done:
                        on_done(ep_id, out)
                    if scheduler:
                        scn_id = plan.episodes[ep_id][0]
                        rep = scheduler.record(scn_id, out.outcome)
                        if rep is not None:
                            new = new_id("ep")
                            plan.episodes[new] = (scn_id, rep)
                            db.add_episode(new, plan.run_id, scn_id, rep)
                            spawn(new)

            for e in sorted(pending):
                spawn(e)
            while tasks:
                await asyncio.gather(*list(tasks))
        for ep_id in plan.episodes:
            snap = await store.load(ep_id)
            if snap.events:
                (plan.out / "episodes").mkdir(exist_ok=True)
                (plan.out / "episodes" / f"{ep_id}.cassette.jsonl").write_text(
                    dump_cassette(snap, {"episode_id": ep_id, "run_id": plan.run_id})
                )
    finally:
        if facade is not None:
            await facade.stop()
        await store.close()


async def _verdicts(path: Path, ids: Sequence[str]) -> dict[str, list[Verdict]]:
    store = await SqliteJournalStore.open(str(path))
    try:
        out: dict[str, list[Verdict]] = {}
        for ep in ids:
            events = (await store.load(ep)).events
            out[ep] = [Verdict.model_validate(e.payload) for e in events if e.kind == "verdict"]
        return out
    finally:
        await store.close()


def build_report(
    plan: RunPlan,
    db: LocalDb,
    *,
    judge_model: str | None,
    unpriced_models: Sequence[str] = (),
) -> RunReport:
    rows = db.episodes(plan.run_id)
    records = [
        EpisodeRecord(
            r.id,
            r.scenario_id,
            r.rep,
            r.outcome or "platform_error",
            r.termination,
            r.cost_usd_micros,
            r.latency_ms,
            r.world_fidelity,
            r.reasons,
        )
        for r in rows
    ]
    verdicts = asyncio.run(_verdicts(plan.out / "journal.db", [r.id for r in rows]))
    cfg = plan.agent.target
    return aggregate_run(
        plan.run_id,
        records,
        verdicts,
        plan.pack.scenarios,
        seed=plan.seed,
        judge_model=judge_model if plan.judge else None,
        target_model=getattr(cfg, "model", None),
        target_kind=cfg.kind,
        wired=bool(getattr(cfg, "wired", False)),
        rubrics=load_rubrics(),
        unpriced_models=unpriced_models,
        adaptive=plan.adaptive,
        repetitions=plan.reps,
    )


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def write_meta(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, default=str))


def read_meta(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


class Timer:
    def __init__(self) -> None:
        self.t0 = time.perf_counter()

    def elapsed(self) -> float:
        return time.perf_counter() - self.t0
