"""Findings: Postgres store, lifecycle, pinning, and the replay and verify runs (P2-5)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from gauntlet_core.schema import Finding, Scenario
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import models as m
from ..db.sec_models import Finding as FindingRow
from ..db.sec_models import FindingEpisode
from ..deps import AppState
from ..errors import ApiError, not_found
from .audit import audit
from .runs import RunCreate, create_run
from .scope import load_doc

__all__ = [
    "ALLOWED",
    "FindingNote",
    "PgFindingStore",
    "change_status",
    "finalize_finding_run",
    "get_finding",
    "link_episode",
    "pin_finding",
    "row_to_finding",
    "start_finding_run",
    "upsert_scenario",
]

ALLOWED: dict[str, tuple[str, ...]] = {
    "open": ("triaged", "in_progress", "fixed", "accepted_risk", "false_positive"),
    "triaged": ("open", "in_progress", "fixed", "accepted_risk", "false_positive"),
    "in_progress": ("triaged", "fixed", "accepted_risk", "false_positive"),
    "fixed": ("open",),
    "verified": ("open",),
    "accepted_risk": ("open",),
    "false_positive": ("open",),
}


class FindingNote(BaseModel):
    ts: str
    actor: str
    note: str
    from_status: str | None = None
    to_status: str | None = None


def row_to_finding(row: FindingRow) -> Finding:
    return Finding.model_validate({**row.doc, "status": row.status})


async def get_finding(session: AsyncSession, ws: str, finding_id: str) -> FindingRow:
    row = await session.get(FindingRow, finding_id)
    if row is None or row.workspace_id != ws:
        raise not_found("finding", finding_id)
    return row


def add_note(
    row: FindingRow, actor: str, note: str, frm: str | None = None, to: str | None = None
) -> None:
    entry = FindingNote(
        ts=datetime.now(UTC).isoformat(), actor=actor, note=note, from_status=frm, to_status=to
    )
    row.notes = [*row.notes, entry.model_dump()]


class PgFindingStore:
    """`FindingStore` (L7) over the findings table. Dedup is by (workspace, key)."""

    def __init__(self, session: AsyncSession, ws: str) -> None:
        self.session, self.ws = session, ws

    async def _row(self, **where: Any) -> FindingRow | None:
        q = select(FindingRow).where(FindingRow.workspace_id == self.ws)
        for k, v in where.items():
            q = q.where(getattr(FindingRow, k) == v)
        return (await self.session.execute(q.limit(1))).scalar_one_or_none()

    async def get_by_dedup(self, key: str) -> Finding | None:
        row = await self._row(dedup_key=key)
        return row_to_finding(row) if row else None

    async def get(self, finding_id: str) -> Finding | None:
        row = await self._row(id=finding_id)
        return row_to_finding(row) if row else None

    async def put(self, finding: Finding) -> None:
        doc = finding.model_dump(mode="json")
        values = dict(
            id=finding.id, workspace_id=self.ws, agent_version_id=finding.agent_version_id,
            category=finding.category, severity=finding.severity, status=finding.status,
            dedup_key=finding.dedup_key, title=finding.title, attack_id=finding.attack_id,
            repro_successes=finding.reproducibility[0], repro_attempts=finding.reproducibility[1],
            doc=doc,
        )  # fmt: skip
        stmt = insert(FindingRow).values(**values)
        await self.session.execute(
            stmt.on_conflict_do_update(
                index_elements=[FindingRow.id],
                set_={
                    "severity": finding.severity, "status": finding.status, "doc": doc,
                    "repro_successes": finding.reproducibility[0],
                    "repro_attempts": finding.reproducibility[1], "updated_at": func.now(),
                },
            )
        )  # fmt: skip
        await self.session.flush()

    async def list(self) -> list[Finding]:
        rows = (
            await self.session.execute(select(FindingRow).where(FindingRow.workspace_id == self.ws))
        ).scalars()
        return [row_to_finding(r) for r in rows]


async def link_episode(
    session: AsyncSession, finding_id: str, episode_id: str, role: str, seqs: list[int]
) -> None:
    stmt = insert(FindingEpisode).values(
        finding_id=finding_id, episode_id=episode_id, role=role, evidence_seqs=seqs
    )
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[FindingEpisode.finding_id, FindingEpisode.episode_id],
            set_={"role": role, "evidence_seqs": seqs},
        )
    )


async def upsert_scenario(
    session: AsyncSession, ws: str, scn: Scenario, source: str, *, status: str = "approved"
) -> int:
    """Insert, or add a new version when the stored document differs. Returns the version."""
    last = (
        await session.execute(
            select(m.Scenario)
            .where(m.Scenario.workspace_id == ws, m.Scenario.id == scn.id)
            .order_by(m.Scenario.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    doc = scn.model_dump(mode="json", exclude_none=True)
    if last is not None:
        same = {**last.doc, "version": 0} == {**doc, "version": 0}
        if same and last.status == status:
            return int(last.version)
    version = (last.version + 1) if last is not None else 1
    doc["version"] = version
    session.add(
        m.Scenario(
            id=scn.id, version=version, workspace_id=ws, doc=doc, status=status, source=source
        )
    )
    await session.flush()
    return version


def suffix(finding_id: str) -> str:
    return finding_id.removeprefix("fnd_")


async def pin_finding(session: AsyncSession, ws: str, row: FindingRow) -> dict[str, str]:
    """Idempotent: the reproducer becomes scenario `scn_pin_<suffix>` of the `security-regression`
    suite of the agent's project (created on first use, repetitions 3)."""
    finding = row_to_finding(row)
    scn = finding.reproducer.model_copy(update={"id": f"scn_pin_{suffix(row.id)}"})
    await upsert_scenario(session, ws, scn, "pinned")
    av = await session.get(m.AgentVersion, row.agent_version_id)
    agent = await session.get(m.Agent, av.agent_id) if av else None
    project = agent.project_id if agent else "none"
    suite_id = f"suite_secreg_{project.removeprefix('proj_')}"
    suite = await session.get(m.Suite, suite_id)
    if suite is None:
        session.add(
            m.Suite(id=suite_id, workspace_id=ws, name="security-regression", repetitions=3)
        )
        await session.flush()
    present = await session.get(m.SuiteScenario, (suite_id, scn.id))
    if present is None:
        n = (
            await session.execute(
                select(func.count())
                .select_from(m.SuiteScenario)
                .where(m.SuiteScenario.suite_id == suite_id)
            )
        ).scalar_one()
        session.add(m.SuiteScenario(suite_id=suite_id, scenario_id=scn.id, position=int(n)))
        await session.flush()
    return {"suite_id": suite_id, "scenario_id": scn.id}


async def change_status(
    session: AsyncSession, ws: str, actor: str, row: FindingRow, to: str, note: str | None
) -> None:
    frm = row.status
    allowed = ALLOWED.get(frm, ())
    if to not in allowed:
        raise ApiError(
            409, "illegal_transition", f"cannot go from {frm} to {to}", {"allowed": list(allowed)}
        )
    await _set_status(session, ws, actor, row, to, note or f"status {frm} to {to}")
    if to == "fixed" and (await load_doc(session, ws)).auto_pin_on_fixed:
        await pin_finding(session, ws, row)


async def _set_status(
    session: AsyncSession, ws: str, actor: str, row: FindingRow, to: str, note: str
) -> None:
    frm = row.status
    row.status = to
    row.doc = {**row.doc, "status": to}
    row.updated_at = datetime.now(UTC)
    add_note(row, actor, note, frm, to)
    await audit(
        session, ws, actor, "finding.status_changed", "finding", row.id, {"from": frm, "to": to}
    )
    await session.flush()


async def start_finding_run(
    session: AsyncSession,
    state: AppState,
    ws: str,
    actor: str,
    row: FindingRow,
    *,
    purpose: str,
    agent_version_id: str | None,
    budget_usd_micros: int | None,
) -> dict[str, Any]:
    """Replay or verify: a one-scenario suite from the reproducer, run on the finding's agent
    version (or another one) `max(5, reproducibility[1])` times. Caller commits."""
    finding = row_to_finding(row)
    scn = finding.reproducer.model_copy(update={"id": f"scn_rep_{suffix(row.id)}"})
    await upsert_scenario(session, ws, scn, "pinned")
    reps = max(5, finding.reproducibility[1])
    from gauntlet_core.ids import new_id

    rid = new_id("run")
    suite_id = f"suite_{purpose}_{rid.removeprefix('run_')}"
    session.add(m.Suite(id=suite_id, workspace_id=ws, name=f"{purpose} {row.id}", repetitions=reps))
    await session.flush()
    session.add(m.SuiteScenario(suite_id=suite_id, scenario_id=scn.id, position=0))
    await session.flush()
    target = agent_version_id or row.agent_version_id
    budget = budget_usd_micros
    if budget is None:
        probe = RunCreate(
            suite_id=suite_id, agent_version_id=target, repetitions=reps, budget_usd_micros=1
        )
        est, _ = await create_run(session, state, ws, probe, dry_run=True)
        budget = max(100_000, 2 * est["estimate_usd_micros"]["expected"])
    body = RunCreate(
        suite_id=suite_id, agent_version_id=target, repetitions=reps, budget_usd_micros=budget
    )
    out, _ = await create_run(
        session, state, ws, body, run_id=rid, purpose=purpose, finding_id=row.id, actor=actor
    )
    return out


async def finalize_finding_run(session: AsyncSession, run_id: str) -> None:
    """Called when a replay or verify run completes: record reproducibility; for verify, flip
    the status (zero successes over at least `reproducibility[1]` counted attempts)."""
    from ..db.sec_models import EpisodeAttack

    run = await session.get(m.Run, run_id)
    if run is None or run.purpose not in ("replay", "verify") or not run.finding_id:
        return
    row = await session.get(FindingRow, run.finding_id)
    if row is None:
        return
    rows = (
        await session.execute(
            select(EpisodeAttack, m.Episode.outcome)
            .join(m.Episode, m.Episode.id == EpisodeAttack.episode_id)
            .where(m.Episode.run_id == run_id, m.Episode.outcome.in_(("passed", "failed")))
        )
    ).all()
    attempts = len(rows)
    successes = sum(1 for ea, _ in rows if ea.objective_held)
    role = "verification" if run.purpose == "verify" else "replay"
    for ea, _ in rows:
        await link_episode(session, row.id, ea.episode_id, role, [])
    finding = row_to_finding(row)
    if run.purpose == "replay":
        row.doc = {**row.doc, "reproducibility": [successes, attempts]}
        row.repro_successes, row.repro_attempts = successes, attempts
        add_note(row, "system", f"replay: {successes} of {attempts} attempts")
        return
    needed = max(1, finding.reproducibility[1])
    if successes > 0:
        await _set_status(
            session, row.workspace_id, "system", row, "open",
            f"verification failed: {successes} of {attempts} attempts still succeed",
        )  # fmt: skip
    elif attempts >= needed:
        await _set_status(
            session, row.workspace_id, "system", row, "verified",
            f"verified: 0 of {attempts} attempts succeed",
        )  # fmt: skip
    else:
        add_note(row, "system", f"verification inconclusive: {attempts} of {needed} attempts ran")
