"""The attack library and taxonomy as the server sees them: loaded from `attacks/` on disk,
imported into the `attacks` table, filtered by what a world can host."""

from __future__ import annotations

import os
from collections.abc import Sequence
from functools import cache
from pathlib import Path
from typing import Any

from gauntlet_core.schema import Attack, WorldSpec
from gauntlet_core.security import AttackLibrary, Taxonomy, load_attacks, load_taxonomy
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.sec_models import Attack as AttackRow

__all__ = [
    "attacks_dir",
    "available_capabilities",
    "import_library",
    "load_workspace_library",
    "taxonomy",
    "upsert_attacks",
]


def attacks_dir() -> Path:
    given = os.environ.get("GAUNTLET_ATTACKS_DIR")
    if given:
        return Path(given)
    here = Path(__file__).resolve()
    for c in (here.parents[5] / "attacks", Path.cwd() / "attacks", Path("/app/attacks")):
        if (c / "taxonomy.yaml").is_file():
            return c
    raise FileNotFoundError("attacks/ not found (set GAUNTLET_ATTACKS_DIR)")


@cache
def taxonomy() -> Taxonomy:
    return load_taxonomy(attacks_dir() / "taxonomy.yaml")


async def upsert_attacks(session: AsyncSession, ws: str, attacks: Sequence[Attack]) -> int:
    n = 0
    for a in attacks:
        stmt = insert(AttackRow).values(
            id=a.id,
            workspace_id=ws,
            doc=a.model_dump(mode="json"),
            category=a.category,
            vector=a.vector,
            source=a.source,
        )
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=[AttackRow.id],
                set_={"doc": stmt.excluded.doc, "category": a.category, "vector": a.vector},
                where=AttackRow.workspace_id == ws,
            )
        )
        n += 1
    return n


async def import_library(session: AsyncSession, ws: str) -> dict[str, Any]:
    """Idempotent upsert of `attacks/library` (by id); returns counts by source."""
    lib = load_attacks(attacks_dir() / "library", taxonomy())
    await upsert_attacks(session, ws, lib.attacks)
    by_source: dict[str, int] = {}
    for a in lib.attacks:
        key = a.source.split("@")[0]
        by_source[key] = by_source.get(key, 0) + 1
    return {"imported": len(lib.attacks), "by_source": by_source, "issues": len(lib.issues)}


async def load_workspace_library(session: AsyncSession, ws: str) -> AttackLibrary:
    rows = (
        await session.execute(
            select(AttackRow).where(AttackRow.workspace_id == ws).order_by(AttackRow.id)
        )
    ).scalars()
    return AttackLibrary([Attack.model_validate(r.doc) for r in rows])


def available_capabilities(world: WorldSpec) -> set[str]:
    caps = {"multi_turn", "tool:read"}
    for t in world.tools:
        caps.add(f"tool:{t.risk}")
        if t.risk == "read":
            caps.add("untrusted_tool_output")  # `place` marks the readers of an injected record
        if t.honeytool:
            caps.add("tool:honeytool")
        if t.untrusted_output:
            caps.add("untrusted_tool_output")
        if "sql" in t.name:
            caps.add("sql_tool")
    if world.documents:
        caps.add("documents")
        caps.add("untrusted_tool_output")  # injectable documents surface through read tools
    if any(c.placement == "system_prompt" for c in world.canaries):
        caps.add("system_prompt_canary")
    return caps
