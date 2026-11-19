"""Seeding helpers for the Postgres integration tests (raw SQL, no ORM, no app code)."""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from functools import cache
from pathlib import Path
from typing import Any

import asyncpg
from alembic import command
from alembic.config import Config
from gauntlet_server.db import Sessionmaker
from sqlalchemy import text
from sqlalchemy.engine import make_url

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def isolated_url(url: str) -> str:
    """The URL of a dedicated `<db>_test` database next to the one in `url`.

    Tests TRUNCATE every table and the compose stack runs a live worker against its own
    database, so tests never share it: that worker would claim the tests' queued episodes.
    """
    u = make_url(url)
    name = u.database or "gauntlet"
    return u.set(database=name if name.endswith("_test") else f"{name}_test").render_as_string(
        hide_password=False
    )


async def _ensure_database(url: str) -> None:
    u = make_url(url)
    admin = u.set(drivername="postgresql", database="postgres")
    conn = await asyncpg.connect(admin.render_as_string(hide_password=False))
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", u.database)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{u.database}"')
    finally:
        await conn.close()


@cache
def database_url() -> str:
    url = isolated_url(os.environ["TEST_DATABASE_URL"])
    with ThreadPoolExecutor(1) as pool:
        pool.submit(asyncio.run, _ensure_database(url)).result()
    return url


def alembic_config(url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def migrate_sync(url: str, op: str, rev: str) -> None:
    """Run an alembic command on a worker thread (env.py starts its own event loop, which
    is not allowed on a thread that already runs one)."""
    fn = {"upgrade": command.upgrade, "downgrade": command.downgrade}[op]
    with ThreadPoolExecutor(1) as pool:
        pool.submit(fn, alembic_config(url), rev).result()


async def migrate(url: str, op: str, rev: str) -> None:
    await asyncio.to_thread(migrate_sync, url, op, rev)


async def reset(sm: Sessionmaker) -> None:
    """Empty every table and seed the parents an episode or run needs."""
    async with sm() as s, s.begin():
        await s.execute(text("TRUNCATE workspaces CASCADE"))
        for sql in (
            "INSERT INTO workspaces (id, name) VALUES ('ws_test', 'test')",
            "INSERT INTO projects (id, workspace_id, name) VALUES ('proj_1', 'ws_test', 'p')",
            "INSERT INTO agents (id, workspace_id, project_id, name) "
            "VALUES ('agent_1', 'ws_test', 'proj_1', 'a')",
            "INSERT INTO agent_versions (id, workspace_id, agent_id, label, config) "
            "VALUES ('av_1', 'ws_test', 'agent_1', 'v1', '{}')",
            "INSERT INTO suites (id, workspace_id, name) VALUES ('suite_1', 'ws_test', 's')",
        ):
            await s.execute(text(sql))


async def add_run(
    sm: Sessionmaker, run_id: str = "run_1", *, budget: int = 1_000_000, status: str = "queued"
) -> None:
    async with sm() as s, s.begin():
        await s.execute(
            text(
                "INSERT INTO runs (id, workspace_id, suite_id, agent_version_id, manifest, status, "
                "budget_usd_micros) VALUES (:id, 'ws_test', 'suite_1', 'av_1', '{}', :st, :b)"
            ),
            {"id": run_id, "st": status, "b": budget},
        )


async def add_episode(sm: Sessionmaker, ep_id: str, run_id: str = "run_1", **cols: Any) -> None:
    """Insert an episode. Extra keyword columns override defaults; `created_at_offset_s` and
    `not_before_offset_s` are seconds relative to the database clock."""
    created = cols.pop("created_at_offset_s", 0)
    not_before = cols.pop("not_before_offset_s", 0)
    names = ["id", "workspace_id", "run_id", "scenario_id", *cols, "created_at", "not_before"]
    values = [
        ":id",
        "'ws_test'",
        ":run",
        "'scn_1'",
        *(f":{k}" for k in cols),
        "now() + :c * interval '1 second'",
        "now() + :nb * interval '1 second'",
    ]
    async with sm() as s, s.begin():
        await s.execute(
            text(f"INSERT INTO episodes ({', '.join(names)}) VALUES ({', '.join(values)})"),
            {"id": ep_id, "run": run_id, "c": created, "nb": not_before, **cols},
        )


async def one(sm: Sessionmaker, sql: str, **params: Any) -> Any:
    async with sm() as s:
        return (await s.execute(text(sql), params)).first()


async def scalar(sm: Sessionmaker, sql: str, **params: Any) -> Any:
    async with sm() as s:
        return (await s.execute(text(sql), params)).scalar()


async def execute(sm: Sessionmaker, sql: str, **params: Any) -> None:
    async with sm() as s, s.begin():
        await s.execute(text(sql), params)
