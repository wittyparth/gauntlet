"""Adaptive sampling on the server (P3-2): after an episode of an adaptive run finishes, decide
under an advisory lock whether its scenario gets one more repetition."""

from __future__ import annotations

from typing import Literal

from gauntlet_core.eval.stability import adaptive_decision
from gauntlet_core.ids import new_id
from gauntlet_core.runner import derive_episode_seed
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Episode

__all__ = ["adaptive_after_episode", "adaptive_step"]

Step = Literal["enqueued", "stopped", "waiting"]


async def adaptive_step(s: AsyncSession, run_id: str, scenario_id: str) -> Step:
    """`waiting`: an episode of this scenario is still queued or leased (at most one extra
    repetition is in flight). `stopped`: the sequential rule, the repetition maximum or the
    `repetitions + 2` episode cap says enough. `enqueued`: the next `rep` row was inserted."""
    await s.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"{run_id}{scenario_id}"}
    )
    run = (
        await s.execute(
            text(
                "SELECT workspace_id, status, repetitions, seed, adaptive FROM runs WHERE id = :r"
            ),
            {"r": run_id},
        )
    ).one()
    ws, status, repetitions, seed, adaptive = run
    if not adaptive or status not in ("queued", "running", "paused"):
        return "stopped"
    rows = (
        await s.execute(
            text(
                "SELECT status, outcome, rep, scenario_version FROM episodes "
                "WHERE run_id = :r AND scenario_id = :sid"
            ),
            {"r": run_id, "sid": scenario_id},
        )
    ).all()
    if any(r[0] in ("queued", "leased") for r in rows):
        return "waiting"
    done = [r for r in rows if r[0] == "done"]
    if any(o == "budget_exhausted" for _, o, _, _ in done):
        return "stopped"
    counted = [r for r in done if r[1] in ("passed", "failed")]
    decision = adaptive_decision(
        passed=sum(1 for r in counted if r[1] == "passed"),
        counted=len(counted),
        excluded=len(done) - len(counted),
        repetitions=repetitions,
    )
    if decision == "stop":
        return "stopped"
    rep = max(r[2] for r in rows) + 1
    s.add(
        Episode(
            id=new_id("ep"),
            workspace_id=ws,
            run_id=run_id,
            scenario_id=scenario_id,
            scenario_version=rows[0][3],
            rep=rep,
            rng_seed=derive_episode_seed(seed, scenario_id, rep),
        )
    )
    await s.flush()
    return "enqueued"


async def adaptive_after_episode(s: AsyncSession, episode_id: str) -> Step | None:
    """The worker hook: a no-op unless the episode's run is adaptive."""
    row = (
        await s.execute(
            text(
                "SELECT e.run_id, e.scenario_id FROM episodes e JOIN runs r ON r.id = e.run_id "
                "WHERE e.id = :e AND r.adaptive"
            ),
            {"e": episode_id},
        )
    ).first()
    return await adaptive_step(s, row[0], row[1]) if row else None
