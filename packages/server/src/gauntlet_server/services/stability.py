"""Quarantine and cross-run stability of a scenario (P3-2)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from gauntlet_core.eval.stability import (
    QuarantineSuggestion,
    ScenarioRunSummary,
    classify_flaky,
    suggest_quarantine,
)
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Scenario, WorkspaceSettings
from ..errors import not_found
from .audit import audit

__all__ = [
    "QuarantineOut",
    "StabilityOut",
    "auto_quarantine_for_run",
    "quarantined_ids",
    "set_quarantine",
    "stability",
]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QuarantineOut(_M):
    scenario_id: str
    quarantined: bool
    reason: str | None
    quarantined_at: str | None


class RunStability(_M):
    run_id: str
    finished_at: str | None
    counted: int
    rate: float | None
    flaky: bool


class Suggestion(_M):
    kind: Literal["flaky", "simulator_errors"]
    reason: str


class StabilityOut(_M):
    scenario_id: str
    agent_version_id: str | None
    quarantined: bool
    quarantine_reason: str | None
    runs: list[RunStability]
    suggestion: Suggestion | None


async def quarantined_ids(s: AsyncSession, ws: str) -> set[str]:
    rows = await s.execute(
        select(Scenario.id).where(Scenario.workspace_id == ws, Scenario.quarantined).distinct()
    )
    return set(rows.scalars())


async def _scenario_exists(s: AsyncSession, ws: str, scenario_id: str) -> None:
    found = (
        await s.execute(
            select(Scenario.id).where(Scenario.workspace_id == ws, Scenario.id == scenario_id)
        )
    ).first()
    if found is None:
        raise not_found("scenario", scenario_id)


async def set_quarantine(
    s: AsyncSession, ws: str, scenario_id: str, on: bool, reason: str, actor: str
) -> QuarantineOut:
    """Every version of the scenario is flagged together; the toggle writes an audit row."""
    await _scenario_exists(s, ws, scenario_id)
    now = datetime.now(UTC)
    await s.execute(
        update(Scenario)
        .where(Scenario.workspace_id == ws, Scenario.id == scenario_id)
        .values(
            quarantined=on,
            quarantine_reason=reason if on else None,
            quarantined_at=now if on else None,
        )
    )
    await audit(
        s, ws, actor, "scenario.quarantined" if on else "scenario.unquarantined",
        "scenario", scenario_id, {"reason": reason},
    )  # fmt: skip
    return QuarantineOut(
        scenario_id=scenario_id,
        quarantined=on,
        reason=reason if on else None,
        quarantined_at=now.isoformat() if on else None,
    )


async def _history(
    s: AsyncSession, ws: str, scenario_id: str, agent_version_id: str, limit: int
) -> tuple[list[RunStability], list[ScenarioRunSummary]]:
    """Newest first: completed eval runs of this agent version holding the scenario at its
    current version."""
    version = (
        await s.execute(
            select(Scenario.version)
            .where(Scenario.workspace_id == ws, Scenario.id == scenario_id)
            .order_by(Scenario.version.desc())
            .limit(1)
        )
    ).scalar_one()
    runs = (
        await s.execute(
            text(
                "SELECT r.id, r.finished_at FROM runs r WHERE r.workspace_id = :ws "
                "AND r.agent_version_id = :av AND r.status = 'done' AND r.purpose = 'eval' "
                "AND EXISTS (SELECT 1 FROM episodes e WHERE e.run_id = r.id "
                "AND e.scenario_id = :sid AND e.scenario_version = :v) "
                "ORDER BY r.finished_at DESC NULLS LAST, r.created_at DESC LIMIT :n"
            ),
            {"ws": ws, "av": agent_version_id, "sid": scenario_id, "v": version, "n": limit},
        )
    ).all()
    rows: list[RunStability] = []
    summaries: list[ScenarioRunSummary] = []
    for run_id, finished in runs:
        outcomes = list(
            (
                await s.execute(
                    text(
                        "SELECT outcome FROM episodes WHERE run_id = :r AND scenario_id = :sid "
                        "AND status = 'done' AND scenario_version = :v ORDER BY rep"
                    ),
                    {"r": run_id, "sid": scenario_id, "v": version},
                )
            ).scalars()
        )
        trials = [o == "passed" for o in outcomes if o in ("passed", "failed")]
        flaky = classify_flaky(trials).flaky
        rows.append(
            RunStability(
                run_id=run_id,
                finished_at=finished.isoformat() if finished else None,
                counted=len(trials),
                rate=sum(trials) / len(trials) if trials else None,
                flaky=flaky,
            )
        )
        summaries.append(ScenarioRunSummary(run_id, flaky, tuple(o or "" for o in outcomes)))
    return rows, summaries


async def stability(
    s: AsyncSession, ws: str, scenario_id: str, agent_version_id: str | None, limit: int
) -> StabilityOut:
    await _scenario_exists(s, ws, scenario_id)
    if agent_version_id is None:  # default: the agent version of the scenario's latest run
        agent_version_id = (
            await s.execute(
                text(
                    "SELECT r.agent_version_id FROM runs r JOIN episodes e ON e.run_id = r.id "
                    "WHERE r.workspace_id = :ws AND e.scenario_id = :sid AND r.status = 'done' "
                    "ORDER BY r.created_at DESC LIMIT 1"
                ),
                {"ws": ws, "sid": scenario_id},
            )
        ).scalar()
    rows: list[RunStability] = []
    suggestion: QuarantineSuggestion | None = None
    if agent_version_id is not None:
        rows, summaries = await _history(s, ws, scenario_id, agent_version_id, limit)
        suggestion = suggest_quarantine(summaries)
    flagged = (
        await s.execute(
            select(Scenario.quarantined, Scenario.quarantine_reason)
            .where(Scenario.workspace_id == ws, Scenario.id == scenario_id)
            .order_by(Scenario.version.desc())
            .limit(1)
        )
    ).one()
    return StabilityOut(
        scenario_id=scenario_id,
        agent_version_id=agent_version_id,
        quarantined=bool(flagged[0]),
        quarantine_reason=flagged[1],
        runs=rows,
        suggestion=Suggestion(kind=suggestion.kind, reason=suggestion.reason)
        if suggestion
        else None,
    )


async def auto_quarantine_for_run(s: AsyncSession, run_id: str) -> list[str]:
    """When the workspace set `auto_quarantine`, apply the suggestions for the scenarios of a
    run that just completed (audited as the `system` actor). Returns the quarantined ids."""
    row = (
        await s.execute(text("SELECT workspace_id, agent_version_id FROM runs WHERE id = :r"),
                        {"r": run_id})
    ).one()  # fmt: skip
    ws, av = row
    settings = await s.get(WorkspaceSettings, ws)
    if not settings or not (settings.doc or {}).get("auto_quarantine"):
        return []
    scenario_ids = (
        await s.execute(
            text("SELECT DISTINCT scenario_id FROM episodes WHERE run_id = :r"), {"r": run_id}
        )
    ).scalars()
    already = await quarantined_ids(s, ws)
    done: list[str] = []
    for sid in sorted(scenario_ids):
        if sid in already:
            continue
        _, summaries = await _history(s, ws, sid, av, 10)
        found = suggest_quarantine(summaries)
        if found:
            await set_quarantine(s, ws, sid, True, f"auto: {found.reason}", "system")
            done.append(sid)
    return done
