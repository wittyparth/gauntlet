"""whoami, projects, agents and their versions, secrets, API keys."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from gauntlet_core.ids import new_id
from gauntlet_core.schema import AgentProfile, TargetConfig
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api_models import (
    AgentList,
    AgentOut,
    AgentVersionList,
    AgentVersionOut,
    ApiKeyCreated,
    ApiKeyList,
    ProjectList,
    ProjectOut,
    SecretList,
    SecretPut,
    WhoAmI,
)
from ..auth import AuthCtx, generate_key, hash_key
from ..db.models import Agent, AgentVersion, ApiKey, Project
from ..deps import AppState, auth_ctx, db_session, get_state
from ..errors import ApiError, not_found
from ..jobs import secret_names
from ..pagination import Page, paginate
from ..services.runs import agent_version_of

router = APIRouter(prefix="/v1")


def _iso(d: Any) -> str | None:
    return d.isoformat() if d else None


# --------------------------------------------------------------------------- whoami


@router.get("/whoami", response_model=WhoAmI)
async def whoami(
    auth: AuthCtx = Depends(auth_ctx), session: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    project = (
        await session.execute(
            select(Project.id)
            .where(Project.workspace_id == auth.workspace_id)
            .order_by(Project.created_at)
            .limit(1)
        )
    ).scalar()
    return {
        "workspace_id": auth.workspace_id,
        "key_id": auth.key_id,
        "key_name": auth.key_name,
        "scopes": auth.scopes,
        "default_project_id": project,
    }


# --------------------------------------------------------------------------- projects


class ProjectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str


def _project(p: Project) -> dict[str, Any]:
    return {"id": p.id, "name": p.name, "created_at": _iso(p.created_at)}


@router.get("/projects", response_model=ProjectList)
async def list_projects(
    limit: int = 50,
    cursor: str | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    q = select(Project).where(Project.workspace_id == auth.workspace_id)
    return await paginate(s, q, Project, Page(limit, cursor), _project)


@router.post("/projects", status_code=201, response_model=ProjectOut)
async def create_project(
    body: ProjectIn, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    p = Project(id=new_id("proj"), workspace_id=auth.workspace_id, name=body.name)
    s.add(p)
    await s.commit()
    await s.refresh(p)
    return _project(p)


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    p = await s.get(Project, project_id)
    if p is None or p.workspace_id != auth.workspace_id:
        raise not_found("project", project_id)
    return _project(p)


# --------------------------------------------------------------------------- agents


class AgentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    name: str
    description: str | None = None


async def _agent_json(s: AsyncSession, a: Agent) -> dict[str, Any]:
    latest_row = (
        await s.execute(
            select(AgentVersion)
            .where(AgentVersion.agent_id == a.id)
            .order_by(AgentVersion.created_at.desc(), AgentVersion.id.desc())
            .limit(1)
        )
    ).scalar()
    latest = latest_row.id if latest_row else None
    purpose = (
        ((latest_row.config or {}).get("profile") or {}).get("purpose") if latest_row else None
    )
    return {
        "id": a.id,
        "project_id": a.project_id,
        "name": a.name,
        "latest_version_id": latest,
        "purpose": purpose,  # from the latest version's profile
        "created_at": _iso(a.created_at),
    }


@router.get("/agents", response_model=AgentList)
async def list_agents(
    limit: int = 50,
    cursor: str | None = None,
    project_id: str | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    q = select(Agent).where(Agent.workspace_id == auth.workspace_id)
    if project_id:
        q = q.where(Agent.project_id == project_id)
    page = await paginate(s, q, Agent, Page(limit, cursor), lambda a: a)
    page["items"] = [await _agent_json(s, a) for a in page["items"]]
    return page


@router.post("/agents", status_code=201, response_model=AgentOut)
async def create_agent(
    body: AgentIn, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    project = await s.get(Project, body.project_id)
    if project is None or project.workspace_id != auth.workspace_id:
        raise not_found("project", body.project_id)
    a = Agent(
        id=new_id("agt"), workspace_id=auth.workspace_id, project_id=project.id, name=body.name
    )
    s.add(a)
    await s.commit()
    await s.refresh(a)
    return await _agent_json(s, a)


async def _agent(s: AsyncSession, auth: AuthCtx, agent_id: str) -> Agent:
    a = await s.get(Agent, agent_id)
    if a is None or a.workspace_id != auth.workspace_id:
        raise not_found("agent", agent_id)
    return a


@router.get("/agents/{agent_id}", response_model=AgentOut)
async def get_agent(
    agent_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    return await _agent_json(s, await _agent(s, auth, agent_id))


class VersionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    target: TargetConfig
    profile: AgentProfile
    world_id: str | None = None


def _version(v: AgentVersion) -> dict[str, Any]:
    out = agent_version_of(v).model_dump(mode="json")
    return {**out, "world_id": v.world_id, "created_at": _iso(v.created_at)}


@router.get("/agents/{agent_id}/versions", response_model=AgentVersionList)
async def list_versions(
    agent_id: str,
    limit: int = 50,
    cursor: str | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    await _agent(s, auth, agent_id)
    q = select(AgentVersion).where(AgentVersion.agent_id == agent_id)
    return await paginate(s, q, AgentVersion, Page(limit, cursor), _version)


@router.post("/agents/{agent_id}/versions", status_code=201, response_model=AgentVersionOut)
async def create_version(
    agent_id: str,
    body: VersionIn,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> dict[str, Any]:
    await _agent(s, auth, agent_id)
    vid = new_id("agv")
    probe = agent_version_model(vid, agent_id, body)
    missing = sorted(
        secret_names(probe) - {n for n, _ in await state.secrets.names(auth.workspace_id)}
    )
    if missing:
        raise ApiError(422, "validation_error", "unknown secret reference", {"missing": missing})
    row = AgentVersion(
        id=vid,
        workspace_id=auth.workspace_id,
        agent_id=agent_id,
        label=body.label,
        config={
            "target": body.target.model_dump(mode="json"),
            "profile": body.profile.model_dump(mode="json"),
        },
        world_id=body.world_id,
    )
    s.add(row)
    await s.commit()
    await s.refresh(row)
    return _version(row)


def agent_version_model(vid: str, agent_id: str, body: VersionIn) -> Any:
    from gauntlet_core.schema import AgentVersion as AgentVersionModel

    return AgentVersionModel(
        id=vid, agent_id=agent_id, label=body.label, target=body.target, profile=body.profile
    )


@router.get("/agents/{agent_id}/versions/{version_id}", response_model=AgentVersionOut)
async def get_version(
    agent_id: str,
    version_id: str,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    await _agent(s, auth, agent_id)
    v = await s.get(AgentVersion, version_id)
    if v is None or v.agent_id != agent_id:
        raise not_found("agent version", version_id)
    return _version(v)


# --------------------------------------------------------------------------- secrets


class SecretIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    value: str


@router.get("/secrets", response_model=SecretList)
async def list_secrets(
    auth: AuthCtx = Depends(auth_ctx), state: AppState = Depends(get_state)
) -> dict[str, Any]:
    names = await state.secrets.names(auth.workspace_id)
    return {"items": [{"name": n, "created_at": _iso(c)} for n, c in names], "next_cursor": None}


@router.post("/secrets", status_code=201, response_model=SecretPut)
async def put_secret(
    body: SecretIn, auth: AuthCtx = Depends(auth_ctx), state: AppState = Depends(get_state)
) -> dict[str, Any]:
    await state.secrets.put(auth.workspace_id, body.name, body.value)
    return {"name": body.name}


@router.delete("/secrets/{name}", status_code=204)
async def delete_secret(
    name: str, auth: AuthCtx = Depends(auth_ctx), state: AppState = Depends(get_state)
) -> None:
    if not await state.secrets.delete(auth.workspace_id, name):
        raise not_found("secret", name)


# --------------------------------------------------------------------------- api keys


class KeyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str


@router.get("/api_keys", response_model=ApiKeyList)
async def list_keys(
    limit: int = Query(50),
    cursor: str | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    q = select(ApiKey).where(ApiKey.workspace_id == auth.workspace_id, ApiKey.revoked_at.is_(None))
    return await paginate(
        s,
        q,
        ApiKey,
        Page(limit, cursor),
        lambda k: {
            "id": k.id,
            "name": k.name,
            "prefix": k.prefix,
            "created_at": _iso(k.created_at),
        },
    )


@router.post("/api_keys", status_code=201, response_model=ApiKeyCreated)
async def create_key(
    body: KeyIn, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    key = generate_key()
    row = ApiKey(
        id=new_id("key"),
        workspace_id=auth.workspace_id,
        hash=hash_key(key),
        prefix=key[:8],
        name=body.name,
        scopes=["admin"],
    )
    s.add(row)
    await s.commit()
    return {"id": row.id, "name": row.name, "prefix": row.prefix, "key": key}


@router.delete("/api_keys/{key_id}", status_code=204)
async def revoke_key(
    key_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> None:
    from datetime import UTC, datetime

    row = await s.get(ApiKey, key_id)
    if row is None or row.workspace_id != auth.workspace_id:
        raise not_found("api key", key_id)
    row.revoked_at = datetime.now(UTC)
    await s.commit()
