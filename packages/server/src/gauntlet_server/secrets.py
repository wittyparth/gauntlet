"""Stored secrets: Fernet ciphertext in `secrets` (contracts section 8). Only the worker
decrypts; values never leave through the API."""

from __future__ import annotations

from collections.abc import Iterable

from cryptography.fernet import Fernet
from gauntlet_core.ids import new_id
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from .db import Sessionmaker
from .db.models import Secret

__all__ = ["SecretStore"]


class SecretStore:
    def __init__(self, sessionmaker: Sessionmaker, key: bytes) -> None:
        self._sm, self._fernet = sessionmaker, Fernet(key)

    async def put(self, workspace_id: str, name: str, value: str) -> None:
        token = self._fernet.encrypt(value.encode()).decode()
        stmt = insert(Secret).values(
            id=new_id("sec"), workspace_id=workspace_id, name=name, ciphertext=token
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["workspace_id", "name"], set_={"ciphertext": token}
        )
        async with self._sm() as s, s.begin():
            await s.execute(stmt)

    async def delete(self, workspace_id: str, name: str) -> bool:
        async with self._sm() as s, s.begin():
            res = await s.execute(
                delete(Secret).where(Secret.workspace_id == workspace_id, Secret.name == name)
            )
            return res.rowcount > 0  # type: ignore[attr-defined]

    async def names(self, workspace_id: str) -> list[tuple[str, object]]:
        async with self._sm() as s:
            rows = await s.execute(
                select(Secret.name, Secret.created_at)
                .where(Secret.workspace_id == workspace_id)
                .order_by(Secret.name)
            )
            return [(r[0], r[1]) for r in rows]

    async def resolve(self, workspace_id: str, names: Iterable[str]) -> dict[str, str]:
        wanted = sorted(set(names))
        if not wanted:
            return {}
        async with self._sm() as s:
            rows = await s.execute(
                select(Secret.name, Secret.ciphertext).where(
                    Secret.workspace_id == workspace_id, Secret.name.in_(wanted)
                )
            )
            return {n: self._fernet.decrypt(c.encode()).decode() for n, c in rows}
