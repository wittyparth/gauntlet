"""API keys: `Authorization: Bearer gk_...`, stored as sha256 hex (keys are high-entropy)."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

from gauntlet_core.ids import new_id
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import ApiKey, Project, Workspace
from .errors import ApiError

__all__ = [
    "AuthCtx",
    "authenticate",
    "ensure_default_workspace",
    "generate_key",
    "hash_key",
    "upsert_key",
]

DEFAULT_WORKSPACE = "ws_default"


@dataclass(frozen=True)
class AuthCtx:
    workspace_id: str
    key_id: str
    key_name: str | None
    scopes: list[str]


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def generate_key() -> str:
    return "gk_" + secrets.token_urlsafe(24)[:32]


async def authenticate(session: AsyncSession, header: str | None) -> AuthCtx:
    if not header or not header.lower().startswith("bearer "):
        raise ApiError(401, "unauthorized", "missing bearer API key")
    key = header[7:].strip()
    row = (
        await session.execute(select(ApiKey).where(ApiKey.hash == hash_key(key)))
    ).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        raise ApiError(401, "unauthorized", "invalid or revoked API key")
    return AuthCtx(row.workspace_id, row.id, row.name, list(row.scopes or []))


async def ensure_default_workspace(session: AsyncSession) -> str:
    """Create `ws_default` and a project `Default` once. Returns the workspace id."""
    if await session.get(Workspace, DEFAULT_WORKSPACE) is None:
        session.add(Workspace(id=DEFAULT_WORKSPACE, name="Default"))
        await session.flush()
        session.add(Project(id=new_id("proj"), workspace_id=DEFAULT_WORKSPACE, name="Default"))
        await session.flush()
    return DEFAULT_WORKSPACE


async def upsert_key(
    session: AsyncSession, workspace_id: str, key: str, name: str = "dev"
) -> ApiKey:
    existing = (
        await session.execute(select(ApiKey).where(ApiKey.hash == hash_key(key)))
    ).scalar_one_or_none()
    if existing is not None:
        if existing.revoked_at is not None:
            await session.execute(
                text("UPDATE api_keys SET revoked_at = NULL WHERE id = :id"), {"id": existing.id}
            )
        return existing
    row = ApiKey(
        id=new_id("key"),
        workspace_id=workspace_id,
        hash=hash_key(key),
        prefix=key[:8],
        name=name,
        scopes=["admin"],
    )
    session.add(row)
    await session.flush()
    return row
