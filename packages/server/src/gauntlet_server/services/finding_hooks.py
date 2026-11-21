"""The worker's post-episode hook (P2-5): record what an attack episode showed, and create or
attach findings. Failures are logged by the caller and never fail the episode."""

from __future__ import annotations

import logging
from typing import Any

from gauntlet_core.eval.cluster import attribute_by_rules, hint_for
from gauntlet_core.schema import Attack, Scenario, WorldSpec
from gauntlet_core.security import (
    AttemptResult,
    file_finding,
    file_forbidden_findings,
    result_from_events,
)
from gauntlet_core.world import build_trajectory, build_world
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from ..db import models as m
from ..db.models import Episode, Run
from ..db.sec_models import Attack as AttackRow
from ..db.sec_models import EpisodeAttack
from ..db.sec_models import Finding as FindingRow
from ..db.session import Sessionmaker
from ..stores import PgJournalStore
from .audit import audit
from .findings import PgFindingStore, add_note, link_episode

__all__ = ["after_episode"]

log = logging.getLogger("gauntlet.findings")


async def _no_oracle(*_a: Any, **_k: Any) -> AttemptResult:  # shrinking is not run in the worker
    raise RuntimeError("the worker hook files findings without shrinking")


async def _latest(session: Any, model: Any, ws: str, id: str) -> Any:
    return (
        await session.execute(
            select(model)
            .where(model.workspace_id == ws, model.id == id)
            .order_by(model.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def after_episode(sm: Sessionmaker, episode_id: str, outcome: str) -> None:
    """Runs before the episode row is marked done (so a run cannot complete without it)."""
    async with sm() as s, s.begin():
        ep = await s.get(Episode, episode_id)
        if ep is None or outcome not in ("passed", "failed"):
            return
        run = await s.get(Run, ep.run_id)
        row = await s.get(m.Scenario, (ep.scenario_id, ep.scenario_version or 1))
        if run is None or row is None:
            return
        scn = Scenario.model_validate(row.doc)
        if scn.attack is None or not isinstance(scn.world, WorldSpec):
            return
        ws = run.workspace_id
        events = (await PgJournalStore(sm).load(episode_id)).events
        world = scn.world
        risk = {t.name: t.risk for t in world.tools}
        result = result_from_events(episode_id, events, risk)
        category = scn.tags.get("attack_category", "")
        vector = scn.tags.get("attack_vector", "")
        stmt = insert(EpisodeAttack).values(
            episode_id=episode_id, workspace_id=ws, attack_id=scn.attack.attack,
            category=category, vector=vector, objective_held=result.objective_held,
        )  # fmt: skip
        await s.execute(
            stmt.on_conflict_do_update(
                index_elements=[EpisodeAttack.episode_id],
                set_={"objective_held": result.objective_held},
            )
        )
        if run.purpose in ("replay", "verify"):
            return  # these runs are accounted for by finalize_finding_run
        await s.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"findings:{ws}"})
        store = PgFindingStore(s, ws)
        created: list[str] = []
        if result.objective_held:
            fid = await _file_attack(s, store, run, scn, result, ws)
            if fid:
                created.append(fid)
        for filing in await file_forbidden_findings(
            store, scn, events, agent_version_id=run.agent_version_id, episode_id=episode_id
        ):
            await link_episode(s, filing.finding.id, episode_id, "evidence", [])
            if filing.created:
                created.append(filing.finding.id)
                await audit(
                    s, ws, "system", "finding.created", "finding", filing.finding.id,
                    {"episode_id": episode_id, "category": filing.finding.category},
                )  # fmt: skip

        if created:
            hint = _root_cause_hint(scn, world, events, int(ep.rng_seed), episode_id)
            for fid in created:
                frow = await s.get(FindingRow, fid, populate_existing=True)
                if hint and frow is not None and not frow.doc.get("root_cause_hint"):
                    frow.doc = {**frow.doc, "root_cause_hint": hint}


def _root_cause_hint(
    scn: Scenario, world: WorldSpec, events: list[Any], rng_seed: int, episode_id: str
) -> str | None:
    """`Finding.root_cause_hint` from the deterministic attribution rules (no model call)."""
    try:
        built = build_world(world, scn.world_overrides, rng_seed)
        traj = build_trajectory(episode_id, scn, events, built)
        checks = [dict(e.payload) for e in events if e.kind == "check_result"]
        attribution = attribute_by_rules(traj, checks)
    except Exception:
        log.warning("attribution failed for %s", episode_id, exc_info=True)
        return None
    return hint_for(attribution) if attribution else None


async def _file_attack(
    s: Any, store: PgFindingStore, run: Run, scn: Scenario, result: AttemptResult, ws: str
) -> str | None:
    assert scn.attack is not None
    arow = await s.get(AttackRow, scn.attack.attack)
    base_world_id = scn.tags.get("base_world")
    base_scn_id = scn.tags.get("base_scenario")
    wrow = await _latest(s, m.World, ws, base_world_id) if base_world_id else None
    brow = await _latest(s, m.Scenario, ws, base_scn_id) if base_scn_id else None
    if arow is None or wrow is None or brow is None:
        log.warning(
            "cannot file finding for %s: attack or base documents are missing", result.episode_id
        )
        return None
    attack = Attack.model_validate(arow.doc)
    filing = await file_finding(
        store, attack, result,
        agent_version_id=run.agent_version_id,
        world=WorldSpec.model_validate(wrow.doc),
        scenario=Scenario.model_validate(brow.doc),
        oracle=_no_oracle,  # type: ignore[arg-type]
        shrink_id=result.episode_id,
        seed=int(scn.tags.get("attack_seed", "0")),
        config=None,
    )  # fmt: skip
    seqs = sorted({e.seq for e in result.evidence})
    fid = filing.finding.id
    await link_episode(s, fid, result.episode_id, "evidence" if filing.created else "variant", seqs)
    if filing.created:
        await audit(
            s, ws, "system", "finding.created", "finding", fid,
            {"episode_id": result.episode_id, "category": filing.finding.category,
             "attack_id": attack.id},
        )  # fmt: skip
    elif filing.finding.status in ("fixed", "verified"):
        frow = await s.get(FindingRow, fid, populate_existing=True)
        if frow is not None:
            frm = frow.status
            frow.status = "open"
            frow.doc = {**frow.doc, "status": "open"}
            add_note(frow, "system", "reopened: the attack succeeded again", frm, "open")
            await audit(
                s, ws, "system", "finding.status_changed", "finding", fid,
                {"from": frm, "to": "open"},
            )  # fmt: skip
    return fid if filing.created else None
