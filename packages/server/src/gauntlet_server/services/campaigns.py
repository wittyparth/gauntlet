"""Campaigns (CQ-S3): attacks times benign scenarios, placed into inline-world scenarios, run as
one `purpose=campaign` run. Episodes are pre-created rows (unknown-episode ruling)."""

from __future__ import annotations

import random
from typing import Any, Literal

from gauntlet_core.ids import new_id
from gauntlet_core.schema import Attack, Scenario, WorldSpec
from gauntlet_core.security import PlacementError, place
from gauntlet_core.security.mutate import apply_mutations
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import models as m
from ..db.sec_models import EpisodeAttack
from ..deps import AppState
from ..errors import ApiError, not_found
from .attack_lib import (
    available_capabilities,
    import_library,
    load_workspace_library,
    taxonomy,
    upsert_attacks,
)
from .findings import upsert_scenario
from .runs import RunCreate, create_run

__all__ = ["CampaignCreate", "build_campaign", "campaign_progress"]


class CampaignCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_version_id: str
    world_id: str
    benign_scenario_ids: list[str] = Field(min_length=1)
    categories: list[str] | None = None
    attack_ids: list[str] | None = None
    mutations: list[str | list[str]] = []
    mode: Literal["static", "adaptive"] = "static"
    repetitions: int = Field(default=1, ge=1)
    budget_usd_micros: int
    max_attacks: int = Field(default=100, ge=1)
    seed: int = 0
    # Where tool_result attacks without their own target inject (a tool name or a state path
    # such as `orders/ord_1001/notes`); default: the first untrusted or read tool of the world.
    inject_target: str | None = None


def with_default_target(attack: Attack, world: WorldSpec, override: str | None = None) -> Attack:
    """Library tool_result attacks carry no target: inject into the first tool that returns
    untrusted output (else the first read tool), so every result of that tool carries it."""
    if attack.vector != "tool_result" or attack.target:
        return attack
    if override:
        return attack.model_copy(update={"target": override})
    names = [t.name for t in world.tools if t.untrusted_output] or [
        t.name for t in world.tools if t.risk == "read"
    ]
    return attack.model_copy(update={"target": names[0]}) if names else attack


async def _latest_doc(s: AsyncSession, model: Any, ws: str, id: str) -> Any:
    return (
        await s.execute(
            select(model)
            .where(model.workspace_id == ws, model.id == id)
            .order_by(model.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def build_campaign(
    s: AsyncSession, state: AppState, ws: str, body: CampaignCreate, actor: str
) -> dict[str, Any]:
    if body.mode == "adaptive":
        raise ApiError(422, "adaptive_unavailable", "adaptive campaigns are not wired yet")
    tax = taxonomy()
    for c in body.categories or []:
        cat = tax.get(c)
        if cat is None or cat.dangerous:
            raise ApiError(422, "unknown_category", f"category {c!r} is not available")
    wrow = await _latest_doc(s, m.World, ws, body.world_id)
    if wrow is None:
        raise not_found("world", body.world_id)
    world = WorldSpec.model_validate(wrow.doc)
    benign: list[Scenario] = []
    for sid in body.benign_scenario_ids:
        row = await _latest_doc(s, m.Scenario, ws, sid)
        if row is None:
            raise not_found("scenario", sid)
        benign.append(Scenario.model_validate(row.doc))

    lib = await load_workspace_library(s, ws)
    if not lib.attacks:
        await import_library(s, ws)
        lib = await load_workspace_library(s, ws)
    chosen = [
        a
        for a in lib.attacks
        if (body.categories is None or a.category in body.categories)
        and (body.attack_ids is None or a.id in body.attack_ids)
        and not (tax.get(a.category) and tax.get(a.category).dangerous)  # type: ignore[union-attr]
    ]
    available = available_capabilities(world)
    skipped: list[dict[str, str]] = []
    usable = []
    for a in chosen:
        missing = sorted(set(a.requires) - available)
        if missing:
            skipped.append({"attack_id": a.id, "reason": f"world lacks {', '.join(missing)}"})
        else:
            usable.append(a)
    if body.mutations:
        usable += await apply_mutations(
            usable, body.mutations, gateway=state.gateway, seed=body.seed
        )
    usable.sort(key=lambda a: a.id)
    if len(usable) > body.max_attacks:
        usable = sorted(
            random.Random(body.seed).sample(usable, body.max_attacks), key=lambda a: a.id
        )

    rid = new_id("run")
    short = rid.removeprefix("run_")
    placed_ids: list[str] = []
    used = []
    for i, attack in enumerate(usable):
        base = benign[i % len(benign)]
        attack = with_default_target(attack, world, body.inject_target)
        try:
            placed = place(attack, world, base, seed=body.seed)
        except PlacementError as e:
            skipped.append({"attack_id": attack.id, "reason": str(e)})
            continue
        tags = {
            **placed.scenario.tags,
            "base_scenario": base.id,
            "base_world": body.world_id,
            "attack_seed": str(body.seed),
            "campaign": rid,
        }
        scn = placed.scenario.model_copy(update={"id": f"scn_cmp_{short}_{i:03d}", "tags": tags})
        await upsert_scenario(s, ws, scn, "generated")
        placed_ids.append(scn.id)
        used.append(attack)
    if not placed_ids:
        raise ApiError(
            422, "no_attacks", "no attack could be placed in this world", {"skipped": skipped}
        )
    await upsert_attacks(s, ws, used)
    suite_id = f"suite_campaign_{short}"
    s.add(
        m.Suite(
            id=suite_id, workspace_id=ws, name=f"campaign {short}", repetitions=body.repetitions
        )
    )
    await s.flush()
    for pos, sid in enumerate(placed_ids):
        s.add(m.SuiteScenario(suite_id=suite_id, scenario_id=sid, position=pos))
    await s.flush()
    run_body = RunCreate(
        suite_id=suite_id,
        agent_version_id=body.agent_version_id,
        repetitions=body.repetitions,
        budget_usd_micros=body.budget_usd_micros,
        seed=body.seed,
    )
    run, _ = await create_run(s, state, ws, run_body, run_id=rid, purpose="campaign", actor=actor)
    return {"campaign_id": rid, "run": run, "attack_count": len(placed_ids), "skipped": skipped}


async def campaign_progress(s: AsyncSession, run_id: str) -> list[dict[str, Any]]:
    rows = (
        await s.execute(
            select(
                EpisodeAttack.category,
                func.count(),
                func.count().filter(EpisodeAttack.objective_held.is_(True)),
            )
            .join(m.Episode, m.Episode.id == EpisodeAttack.episode_id)
            .where(m.Episode.run_id == run_id)
            .group_by(EpisodeAttack.category)
            .order_by(EpisodeAttack.category)
        )
    ).all()
    return [{"category": c, "attempts": int(a), "successes": int(k)} for c, a, k in rows]
