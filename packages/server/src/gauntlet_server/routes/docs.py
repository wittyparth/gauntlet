"""Versioned documents (worlds, personas, rubrics, scenarios) and suites."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from gauntlet_core.schema import Persona, Rubric, Scenario, Suite, WorldSpec
from gauntlet_core.validate import validate_scenario
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ..auth import AuthCtx
from ..db import models as m
from ..deps import auth_ctx, db_session
from ..errors import ApiError, not_found
from ..pagination import Page, paginate

router = APIRouter(prefix="/v1")

_CHANGES_REVIEW = ("success", "forbidden", "world")


def _latest(model: Any, ws: str) -> Any:
    other = aliased(model)
    newest = select(func.max(other.version)).where(other.id == model.id, other.workspace_id == ws)
    return select(model).where(model.workspace_id == ws, model.version == newest.scalar_subquery())


async def _next_version(s: AsyncSession, model: Any, ws: str, id: str) -> int:
    cur = (
        await s.execute(
            select(func.max(model.version)).where(model.workspace_id == ws, model.id == id)
        )
    ).scalar()
    return int(cur or 0) + 1


async def _get_latest(s: AsyncSession, model: Any, ws: str, id: str) -> Any:
    row = (
        await s.execute(
            select(model)
            .where(model.workspace_id == ws, model.id == id)
            .order_by(model.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return row


def _parse(model: Any, data: Any) -> Any:
    try:
        return model.model_validate(data)
    except ValidationError as e:
        raise ApiError(
            422,
            "validation_error",
            "invalid document",
            e.errors(include_url=False, include_context=False),
        ) from e


def _doc(row: Any) -> dict[str, Any]:
    return {**row.doc, "version": row.version, "created_at": row.created_at.isoformat()}


# ------------------------------------------------------- generic versioned documents


def _register(path: str, table: Any, schema: Any, what: str, set_version: bool) -> None:
    @router.get(f"/{path}", name=f"list_{path}")
    async def list_docs(
        limit: int = 50,
        cursor: str | None = None,
        auth: AuthCtx = Depends(auth_ctx),
        s: AsyncSession = Depends(db_session),
    ) -> dict[str, Any]:
        return await paginate(
            s, _latest(table, auth.workspace_id), table, Page(limit, cursor), _doc
        )

    @router.get(f"/{path}/{{doc_id}}", name=f"get_{path}")
    async def get_doc(
        doc_id: str,
        version: int | None = None,
        auth: AuthCtx = Depends(auth_ctx),
        s: AsyncSession = Depends(db_session),
    ) -> dict[str, Any]:
        if version is None:
            row = await _get_latest(s, table, auth.workspace_id, doc_id)
        else:
            row = await s.get(table, (doc_id, version))
            if row is not None and row.workspace_id != auth.workspace_id:
                row = None
        if row is None:
            raise not_found(what, doc_id)
        return _doc(row)

    @router.post(f"/{path}", status_code=201, name=f"create_{path}")
    async def create_doc(
        body: dict[str, Any] = Body(...),
        auth: AuthCtx = Depends(auth_ctx),
        s: AsyncSession = Depends(db_session),
    ) -> dict[str, Any]:
        model = _parse(schema, body)
        if not model.id:
            raise ApiError(422, "validation_error", f"{what} needs an id")
        version = await _next_version(s, table, auth.workspace_id, model.id)
        data = model.model_dump(mode="json", exclude_none=True)
        if set_version:
            data["version"] = version
        row = table(id=model.id, version=version, workspace_id=auth.workspace_id, doc=data)
        s.add(row)
        await s.commit()
        await s.refresh(row)
        return _doc(row)


_register("worlds", m.World, WorldSpec, "world", False)
_register("personas", m.Persona, Persona, "persona", False)
_register("rubrics", m.Rubric, Rubric, "rubric", True)


@router.post("/worlds/import-openapi", status_code=501)
async def import_openapi(_: AuthCtx = Depends(auth_ctx)) -> None:
    raise ApiError(501, "not_implemented", "OpenAPI import arrives with the packs batch")


# --------------------------------------------------------------------------- scenarios


def _scenario(row: m.Scenario) -> dict[str, Any]:
    return {
        "scenario": row.doc,
        "id": row.id,
        "status": row.status,
        "source": row.source,
        "version": row.version,
        "created_at": row.created_at.isoformat(),
    }


@router.get("/scenarios")
async def list_scenarios(
    limit: int = 50,
    cursor: str | None = None,
    status: str | None = None,
    source: str | None = None,
    tag: list[str] = Query(default=[]),
    q: str | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    query = _latest(m.Scenario, auth.workspace_id)
    if status:
        query = query.where(m.Scenario.status == status)
    if source:
        query = query.where(m.Scenario.source == source)
    for t in tag:
        key, _, value = t.partition(":")
        query = query.where(m.Scenario.doc["tags"][key].astext == value)
    if q:
        like = f"%{q}%"
        query = query.where(m.Scenario.doc["title"].astext.ilike(like) | m.Scenario.id.ilike(like))
    return await paginate(s, query, m.Scenario, Page(limit, cursor), _scenario)


@router.post("/scenarios", status_code=201)
async def create_scenario(
    body: dict[str, Any] = Body(...),
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    data = dict(body)
    source = data.pop("source", "generated")
    if source not in ("pack", "generated", "mined", "pinned"):
        raise ApiError(422, "validation_error", f"invalid source {source!r}")
    scn = _parse(Scenario, data)
    version = await _next_version(s, m.Scenario, auth.workspace_id, scn.id)
    scn = scn.model_copy(update={"version": version})
    row = m.Scenario(
        id=scn.id,
        version=version,
        workspace_id=auth.workspace_id,
        doc=scn.model_dump(mode="json", exclude_none=True),
        status="approved" if source == "pack" else "draft",
        source=source,
    )
    s.add(row)
    await s.commit()
    await s.refresh(row)
    return _scenario(row)


@router.get("/scenarios/{scenario_id}")
async def get_scenario(
    scenario_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    row = await _get_latest(s, m.Scenario, auth.workspace_id, scenario_id)
    if row is None:
        raise not_found("scenario", scenario_id)
    return _scenario(row)


@router.put("/scenarios/{scenario_id}")
async def put_scenario(
    scenario_id: str,
    body: dict[str, Any] = Body(...),
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    prev = await _get_latest(s, m.Scenario, auth.workspace_id, scenario_id)
    if prev is None:
        raise not_found("scenario", scenario_id)
    data = {k: v for k, v in body.items() if k != "source"}
    scn = _parse(Scenario, {**data, "id": scenario_id})
    version = prev.version + 1
    scn = scn.model_copy(update={"version": version})
    doc = scn.model_dump(mode="json", exclude_none=True)
    keeps_approval = prev.status == "approved" and all(
        doc[k] == prev.doc.get(k) for k in _CHANGES_REVIEW
    )
    row = m.Scenario(
        id=scenario_id,
        version=version,
        workspace_id=auth.workspace_id,
        doc=doc,
        status="approved" if keeps_approval else "draft",
        source=body.get("source", prev.source),
    )
    s.add(row)
    await s.commit()
    await s.refresh(row)
    return _scenario(row)


async def _approve(s: AsyncSession, ws: str, ids: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    for sid in ids:
        row = await _get_latest(s, m.Scenario, ws, sid)
        if row is None:
            raise not_found("scenario", sid)
        scn = Scenario.model_validate(row.doc)
        if isinstance(scn.world, str):
            wrow = await _get_latest(s, m.World, ws, scn.world)
            if wrow is None:
                problems.append({"scenario_id": sid, "code": "unknown_world", "message": scn.world})
                continue
            spec = WorldSpec.model_validate(wrow.doc)
        else:
            spec = scn.world
        for issue in validate_scenario(scn, spec):
            problems.append({"scenario_id": sid, "code": issue.code, "message": issue.message})
        out.append({"row": row})
    if problems:
        raise ApiError(422, "validation_error", "scenarios failed validation", problems)
    for item in out:
        item["row"].status = "approved"
    await s.commit()
    return [_scenario(i["row"]) for i in out]


class BulkIds(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str]


@router.post("/scenarios/bulk-approve")
async def bulk_approve(
    body: BulkIds, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    return {"items": await _approve(s, auth.workspace_id, body.ids), "next_cursor": None}


@router.post("/scenarios/{scenario_id}/approve")
async def approve(
    scenario_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    return (await _approve(s, auth.workspace_id, [scenario_id]))[0]


# ----------------------------------------------------------------------------- suites


def _suite(row: m.Suite, scenarios: list[str]) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "scenarios": scenarios,
        "repetitions": row.repetitions,
        "persona_mix": row.persona_mix,
        "created_at": row.created_at.isoformat(),
    }


async def _suite_ids(s: AsyncSession, suite_id: str) -> list[str]:
    return list(
        (
            await s.execute(
                select(m.SuiteScenario.scenario_id)
                .where(m.SuiteScenario.suite_id == suite_id)
                .order_by(m.SuiteScenario.position)
            )
        ).scalars()
    )


async def _check_scenarios(s: AsyncSession, ws: str, ids: list[str]) -> None:
    known = set(
        (
            await s.execute(
                select(m.Scenario.id).where(m.Scenario.workspace_id == ws, m.Scenario.id.in_(ids))
            )
        ).scalars()
    )
    unknown = [i for i in ids if i not in known]
    if unknown:
        raise ApiError(422, "validation_error", "unknown scenario ids", {"unknown": unknown})


async def _set_scenarios(s: AsyncSession, suite_id: str, ids: list[str]) -> None:
    for old in (
        await s.execute(select(m.SuiteScenario).where(m.SuiteScenario.suite_id == suite_id))
    ).scalars():
        await s.delete(old)
    await s.flush()
    for pos, sid in enumerate(ids):
        s.add(m.SuiteScenario(suite_id=suite_id, scenario_id=sid, position=pos))


@router.get("/suites")
async def list_suites(
    limit: int = 50,
    cursor: str | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    q = select(m.Suite).where(m.Suite.workspace_id == auth.workspace_id)
    page = await paginate(s, q, m.Suite, Page(limit, cursor), lambda r: r)
    page["items"] = [_suite(r, await _suite_ids(s, r.id)) for r in page["items"]]
    return page


@router.post("/suites", status_code=201)
async def create_suite(
    body: Suite, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    if await s.get(m.Suite, body.id) is not None:
        raise ApiError(409, "conflict", f"suite {body.id!r} exists")
    await _check_scenarios(s, auth.workspace_id, body.scenarios)
    row = m.Suite(
        id=body.id,
        workspace_id=auth.workspace_id,
        name=body.name,
        repetitions=body.repetitions,
        persona_mix=body.persona_mix,
    )
    s.add(row)
    await s.flush()
    await _set_scenarios(s, body.id, body.scenarios)
    await s.commit()
    await s.refresh(row)
    return _suite(row, body.scenarios)


async def _suite_row(s: AsyncSession, auth: AuthCtx, suite_id: str) -> m.Suite:
    row = await s.get(m.Suite, suite_id)
    if row is None or row.workspace_id != auth.workspace_id:
        raise not_found("suite", suite_id)
    return row


@router.get("/suites/{suite_id}")
async def get_suite(
    suite_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    row = await _suite_row(s, auth, suite_id)
    return _suite(row, await _suite_ids(s, suite_id))


@router.put("/suites/{suite_id}")
async def put_suite(
    suite_id: str,
    body: Suite,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    row = await _suite_row(s, auth, suite_id)
    await _check_scenarios(s, auth.workspace_id, body.scenarios)
    row.name, row.repetitions, row.persona_mix = body.name, body.repetitions, body.persona_mix
    await _set_scenarios(s, suite_id, body.scenarios)
    await s.commit()
    return _suite(row, body.scenarios)
