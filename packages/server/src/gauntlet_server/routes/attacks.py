"""Attack library, taxonomy and campaigns."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from gauntlet_core.schema import Attack
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api_models import RunOut
from ..auth import AuthCtx
from ..db.models import Run
from ..db.sec_models import Attack as AttackRow
from ..deps import AppState, auth_ctx, db_session, get_state
from ..errors import not_found
from ..pagination import Page, paginate
from ..services.attack_lib import import_library, taxonomy
from ..services.campaigns import CampaignCreate, build_campaign, campaign_progress
from ..services.runs import run_json

router = APIRouter(prefix="/v1")


class AttackListOut(BaseModel):
    items: list[Attack]
    next_cursor: str | None


class ImportOut(BaseModel):
    imported: int
    by_source: dict[str, int]
    issues: int


class CategoryOut(BaseModel):
    id: str
    number: int
    title: str
    description: str
    owasp_llm: list[str]
    owasp_agentic: list[str]
    atlas: list[str]
    phase_scope: str
    dangerous: bool


class TaxonomyOut(BaseModel):
    verified_on: str
    categories: list[CategoryOut]


class Skipped(BaseModel):
    attack_id: str
    reason: str


class CampaignOut(BaseModel):
    campaign_id: str
    run: RunOut
    attack_count: int
    skipped: list[Skipped]


class CategoryProgress(BaseModel):
    category: str
    attempts: int
    successes: int


class CampaignStatus(BaseModel):
    campaign_id: str
    run: RunOut
    progress: list[CategoryProgress]


@router.get("/attacks", response_model=AttackListOut)
async def list_attacks(
    category: str | None = None,
    vector: str | None = None,
    source: str | None = None,
    q: str | None = None,
    requires: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    query = select(AttackRow).where(AttackRow.workspace_id == auth.workspace_id)
    if category:
        query = query.where(AttackRow.category == category)
    if vector:
        query = query.where(AttackRow.vector == vector)
    if source:
        query = query.where(AttackRow.source.startswith(source))
    if q:
        query = query.where(AttackRow.doc.cast(AttackRow.source.type).ilike(f"%{q}%"))
    if requires is not None:  # attacks whose requirements are all in this comma list
        have = {x for x in requires.split(",") if x}
        page = await paginate(s, query, AttackRow, Page(200), lambda r: r.doc)
        items = [d for d in page["items"] if set(d.get("requires", [])) <= have]
        return {"items": items[: max(1, min(limit, 200))], "next_cursor": None}
    return await paginate(s, query, AttackRow, Page(limit, cursor), lambda r: r.doc)


@router.get("/attacks/{attack_id}", response_model=Attack)
async def get_attack(
    attack_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    row = await s.get(AttackRow, attack_id)
    if row is None or row.workspace_id != auth.workspace_id:
        raise not_found("attack", attack_id)
    return row.doc


@router.post("/attacks/import", response_model=ImportOut)
async def import_attacks(
    auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    out = await import_library(s, auth.workspace_id)
    await s.commit()
    return out


@router.get("/security/taxonomy", response_model=TaxonomyOut)
async def get_taxonomy(_: AuthCtx = Depends(auth_ctx)) -> dict[str, Any]:
    t = taxonomy()
    return {
        "verified_on": t.verified_on,
        "categories": [
            {
                "id": c.id, "number": c.number, "title": c.title, "description": c.description,
                "owasp_llm": list(c.owasp_llm), "owasp_agentic": list(c.owasp_agentic),
                "atlas": list(c.atlas), "phase_scope": c.phase_scope, "dangerous": c.dangerous,
            }
            for c in t.categories
        ],
    }  # fmt: skip


@router.post("/campaigns", status_code=201, response_model=CampaignOut)
async def create_campaign(
    body: CampaignCreate,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> dict[str, Any]:
    out = await build_campaign(s, state, auth.workspace_id, body, auth.key_name or auth.key_id)
    await s.commit()
    return out


@router.get("/campaigns/{campaign_id}", response_model=CampaignStatus)
async def get_campaign(
    campaign_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    run = await s.get(Run, campaign_id)
    if run is None or run.workspace_id != auth.workspace_id or run.purpose != "campaign":
        raise not_found("campaign", campaign_id)
    return {
        "campaign_id": run.id,
        "run": await run_json(s, run),
        "progress": await campaign_progress(s, run.id),
    }
