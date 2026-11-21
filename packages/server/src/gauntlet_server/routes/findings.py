"""Findings API: list, detail, lifecycle, replay, verify, pin, exports."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Response
from gauntlet_core.schema import Finding, PolicyRule, Scenario
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api_models import RunOut
from ..auth import AuthCtx
from ..db.sec_models import Finding as FindingRow
from ..db.sec_models import FindingEpisode
from ..deps import AppState, auth_ctx, db_session, get_state
from ..errors import ApiError
from ..pagination import Page, paginate
from ..services.attack_lib import taxonomy
from ..services.audit import audit
from ..services.findings import (
    change_status,
    get_finding,
    pin_finding,
    row_to_finding,
    start_finding_run,
)
from ..services.markdown_export import (
    gather_bundle,
    render_json,
    render_markdown,
    render_sarif,
)
from ..services.runs import platform_version

router = APIRouter(prefix="/v1")

STATUSES = (
    "open",
    "triaged",
    "in_progress",
    "fixed",
    "verified",
    "accepted_risk",
    "false_positive",
)


class NoteOut(BaseModel):
    ts: str
    actor: str
    note: str
    from_status: str | None = None
    to_status: str | None = None


class FindingSummaryOut(BaseModel):
    id: str
    title: str
    category: str
    severity: str
    status: str
    agent_version_id: str
    attack_id: str | None
    reproducibility: tuple[int, int]
    dedup_key: str
    root_cause_hint: str | None
    created_at: str
    updated_at: str


class FindingEpisodeOut(BaseModel):
    episode_id: str
    role: str
    evidence_seqs: list[int]


class FindingDetailOut(FindingSummaryOut):
    reproducer: Scenario
    suggested_policy: PolicyRule | None
    episodes: list[FindingEpisodeOut]
    notes: list[NoteOut]


class FindingListOut(BaseModel):
    items: list[FindingSummaryOut]
    next_cursor: str | None


class StatusPatch(BaseModel):
    status: str
    note: str | None = None


class ReplayBody(BaseModel):
    budget_usd_micros: int | None = None
    agent_version_id: str | None = None


class FindingExportJson(FindingSummaryOut):
    reproducer: Scenario
    episodes: list[FindingEpisodeOut]


# md -> text/markdown (str); json -> FindingExportJson (a list for the bulk route); sarif -> object
ExportOut = FindingExportJson | list[FindingExportJson] | dict[str, Any] | str


class PinOut(BaseModel):
    suite_id: str
    scenario_id: str


def summary(row: FindingRow) -> dict[str, Any]:
    f: Finding = row_to_finding(row)
    return {
        "id": row.id, "title": row.title, "category": row.category, "severity": row.severity,
        "status": row.status, "agent_version_id": row.agent_version_id, "attack_id": row.attack_id,
        "reproducibility": [row.repro_successes, row.repro_attempts], "dedup_key": row.dedup_key,
        "root_cause_hint": f.root_cause_hint, "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }  # fmt: skip


def _filtered(
    auth: AuthCtx,
    status: str | None,
    severity: str | None,
    category: str | None,
    agent_version_id: str | None,
    q: str | None = None,
) -> Any:
    query = select(FindingRow).where(FindingRow.workspace_id == auth.workspace_id)
    if status:
        query = query.where(FindingRow.status == status)
    if severity:
        query = query.where(FindingRow.severity == severity)
    if category:
        query = query.where(FindingRow.category == category)
    if agent_version_id:
        query = query.where(FindingRow.agent_version_id == agent_version_id)
    if q:
        like = f"%{q}%"
        query = query.where(or_(FindingRow.title.ilike(like), FindingRow.id.ilike(like)))
    return query


@router.get("/findings", response_model=FindingListOut)
async def list_findings(
    status: str | None = None,
    severity: str | None = None,
    category: str | None = None,
    agent_version_id: str | None = None,
    q: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    query = _filtered(auth, status, severity, category, agent_version_id, q)
    return await paginate(s, query, FindingRow, Page(limit, cursor), summary)


@router.get("/findings/export", response_model=ExportOut)
async def export_findings(
    format: Literal["sarif", "json"] = "sarif",
    status: str | None = None,
    agent_version_id: str | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> Response:
    rows = (await s.execute(_filtered(auth, status, None, None, agent_version_id))).scalars().all()
    bundles = [await gather_bundle(s, r) for r in rows]
    if format == "sarif":
        doc: Any = render_sarif(bundles, taxonomy(), platform_version())
    else:
        doc = [render_json(b) for b in bundles]
    import json

    return Response(json.dumps(doc), media_type="application/json")


async def _detail(s: AsyncSession, row: FindingRow) -> dict[str, Any]:
    f = row_to_finding(row)
    eps = (
        (
            await s.execute(
                select(FindingEpisode)
                .where(FindingEpisode.finding_id == row.id)
                .order_by(FindingEpisode.created_at, FindingEpisode.episode_id)
            )
        )
        .scalars()
        .all()
    )
    return {
        **summary(row),
        "reproducer": f.reproducer,
        "suggested_policy": f.suggested_policy,
        "notes": row.notes,
        "episodes": [
            {"episode_id": e.episode_id, "role": e.role, "evidence_seqs": list(e.evidence_seqs)}
            for e in eps
        ],
    }


@router.get("/findings/{finding_id}", response_model=FindingDetailOut)
async def get_finding_route(
    finding_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    return await _detail(s, await get_finding(s, auth.workspace_id, finding_id))


@router.patch("/findings/{finding_id}", response_model=FindingDetailOut)
async def patch_finding(
    finding_id: str,
    body: StatusPatch,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    row = await get_finding(s, auth.workspace_id, finding_id)
    if body.status not in STATUSES:
        raise ApiError(422, "validation_error", f"unknown status {body.status!r}")
    await change_status(
        s, auth.workspace_id, auth.key_name or auth.key_id, row, body.status, body.note
    )
    await s.commit()
    return await _detail(s, row)


async def _launch(
    finding_id: str, purpose: str, body: ReplayBody, auth: AuthCtx, s: AsyncSession, state: AppState
) -> dict[str, Any]:
    row = await get_finding(s, auth.workspace_id, finding_id)
    out = await start_finding_run(
        s, state, auth.workspace_id, auth.key_name or auth.key_id, row,
        purpose=purpose, agent_version_id=body.agent_version_id,
        budget_usd_micros=body.budget_usd_micros,
    )  # fmt: skip
    await s.commit()
    return out


@router.post("/findings/{finding_id}/replay", status_code=201, response_model=RunOut)
async def replay(
    finding_id: str,
    body: ReplayBody | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> dict[str, Any]:
    return await _launch(finding_id, "replay", body or ReplayBody(), auth, s, state)


@router.post("/findings/{finding_id}/verify", status_code=201, response_model=RunOut)
async def verify_route(
    finding_id: str,
    body: ReplayBody | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> dict[str, Any]:
    return await _launch(finding_id, "verify", body or ReplayBody(), auth, s, state)


@router.post("/findings/{finding_id}/pin", response_model=PinOut)
async def pin(
    finding_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> dict[str, str]:
    row = await get_finding(s, auth.workspace_id, finding_id)
    out = await pin_finding(s, auth.workspace_id, row)
    await audit(
        s, auth.workspace_id, auth.key_name or auth.key_id, "finding.pinned", "finding", row.id,
        out,
    )  # fmt: skip
    await s.commit()
    return out


@router.get("/findings/{finding_id}/export", response_model=ExportOut)
async def export_finding(
    finding_id: str,
    format: Literal["md", "json", "sarif"] = "md",
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> Response:
    import json

    row = await get_finding(s, auth.workspace_id, finding_id)
    b = await gather_bundle(s, row)
    if format == "md":
        return Response(render_markdown(b, taxonomy()), media_type="text/markdown")
    if format == "json":
        return Response(json.dumps(render_json(b)), media_type="application/json")
    doc = render_sarif([b], taxonomy(), platform_version())
    return Response(json.dumps(doc), media_type="application/sarif+json")
