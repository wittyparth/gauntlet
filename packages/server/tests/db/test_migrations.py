"""Alembic migrations against a throwaway database (the shared test database is untouched)."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor

import pytest
import pytest_asyncio
from alembic import command
from pg_helpers import alembic_config, database_url, migrate
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

pytestmark = pytest.mark.integration

CONTRACT_TABLES = {
    "workspaces", "api_keys", "projects", "agents", "agent_versions", "personas", "worlds",
    "rubrics", "scenarios", "suites", "suite_scenarios", "runs", "episodes", "events",
    "effects", "verdicts", "secrets", "events_archive", "effects_archive", "workspace_settings",
    "target_verifications", "audit_log", "kill_switches", "findings", "finding_episodes",
    "attacks", "episode_attacks", "human_labels", "calibrations", "jobs",
    "failure_embeddings", "failure_clusters", "badge_tokens", "policies", "policy_proposals",
    "gateway_decisions", "gateway_approvals", "policy_tests",
    "prod_conversations", "prod_events", "prod_spans_seen", "ingest_stats",
    "mining_runs", "mining_candidates",
    "schedules", "slos", "alert_channels", "alert_rules", "alerts", "evidence_packs",
}  # fmt: skip


@pytest_asyncio.fixture
async def scratch() -> AsyncIterator[tuple[str, AsyncEngine]]:
    base = make_url(database_url())
    name = f"gauntlet_mig_{uuid.uuid4().hex[:8]}"
    admin = create_async_engine(base, isolation_level="AUTOCOMMIT")
    async with admin.connect() as c:
        await c.execute(text(f'CREATE DATABASE "{name}"'))
    url = base.set(database=name).render_as_string(hide_password=False)
    engine = create_async_engine(url)
    yield url, engine
    await engine.dispose()
    async with admin.connect() as c:
        await c.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
    await admin.dispose()


async def tables(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as c:
        rows = await c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        return {r[0] for r in rows} - {"alembic_version"}


async def test_up_down_up(scratch):
    url, engine = scratch
    await migrate(url, "upgrade", "head")
    assert await tables(engine) == CONTRACT_TABLES
    await migrate(url, "downgrade", "base")
    assert await tables(engine) == set()
    await migrate(url, "upgrade", "head")
    assert await tables(engine) == CONTRACT_TABLES


async def test_alembic_check_is_clean(scratch):
    url, _ = scratch
    await migrate(url, "upgrade", "head")
    # raises CommandError if the models and the migrations disagree
    await asyncio.to_thread(lambda: _check(url))


def _check(url: str) -> None:
    with ThreadPoolExecutor(1) as pool:
        pool.submit(command.check, alembic_config(url)).result()


async def test_vector_extension_installed(scratch):
    url, engine = scratch
    await migrate(url, "upgrade", "head")
    async with engine.connect() as c:
        assert (await c.execute(text("SELECT 1 FROM pg_extension WHERE extname='vector'"))).first()


async def test_key_constraints(scratch):
    url, engine = scratch
    await migrate(url, "upgrade", "head")
    async with engine.connect() as c:
        rows = await c.execute(
            text(
                "SELECT tc.table_name, tc.constraint_type, "
                "array_agg(k.column_name::text ORDER BY k.ordinal_position) "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage k USING (constraint_name, table_name) "
                "WHERE tc.table_schema = 'public' "
                "AND tc.constraint_type IN ('PRIMARY KEY','UNIQUE') "
                "GROUP BY tc.table_name, tc.constraint_name, tc.constraint_type"
            )
        )
        keys = {(r[0], r[1], tuple(r[2])) for r in rows}
    assert ("episodes", "PRIMARY KEY", ("id",)) in keys
    assert ("events", "PRIMARY KEY", ("episode_id", "seq")) in keys
    assert ("effects", "PRIMARY KEY", ("episode_id", "key")) in keys
    for t in ("personas", "worlds", "rubrics", "scenarios"):
        assert (t, "PRIMARY KEY", ("id", "version")) in keys
    assert ("secrets", "UNIQUE", ("workspace_id", "name")) in keys
    assert ("api_keys", "UNIQUE", ("hash",)) in keys


async def test_claim_index_is_partial(scratch):
    url, engine = scratch
    await migrate(url, "upgrade", "head")
    async with engine.connect() as c:
        d = (
            await c.execute(
                text("SELECT indexdef FROM pg_indexes WHERE indexname='ix_episodes_claim'")
            )
        ).scalar()
    assert d and "WHERE" in d and "queued" in d


async def test_backfill_latency_and_tokens(scratch):
    url, engine = scratch
    await migrate(url, "upgrade", "0005")
    ev = lambda seq, kind, wall: json.dumps(  # noqa: E731
        {"seq": seq, "kind": kind, "actor": "agent", "wall_ms": wall, "payload": {}}
    )
    async with engine.begin() as c:
        for sql in (
            "INSERT INTO workspaces (id, name) VALUES ('w', 'w')",
            "INSERT INTO projects (id, workspace_id, name) VALUES ('p', 'w', 'p')",
            "INSERT INTO agents (id, workspace_id, project_id, name) VALUES ('a', 'w', 'p', 'a')",
            "INSERT INTO agent_versions (id, workspace_id, agent_id, label, config) "
            "VALUES ('av', 'w', 'a', 'v', '{}')",
            "INSERT INTO suites (id, workspace_id, name) VALUES ('s', 'w', 's')",
            "INSERT INTO runs (id, workspace_id, suite_id, agent_version_id, manifest, "
            "budget_usd_micros) VALUES ('r', 'w', 's', 'av', '{}', 1)",
            "INSERT INTO episodes (id, workspace_id, run_id, scenario_id, status) "
            "VALUES ('e1', 'w', 'r', 'x', 'done'), ('e2', 'w', 'r', 'x', 'queued')",
        ):
            await c.execute(text(sql))
        for seq, kind, wall in [(0, "user_message", 900), (1, "agent_message", 120),
                                (2, "tool_result", 30), (3, "agent_message", 50)]:  # fmt: skip
            await c.execute(
                text("INSERT INTO events (episode_id, seq, kind, doc) "
                     "VALUES ('e1', :s, :k, CAST(:d AS jsonb))"),
                {"s": seq, "k": kind, "d": ev(seq, kind, wall)},
            )  # fmt: skip
        costs = [("llm:0", (100, 10)), ("llm:1", (50, 5))]
        for key, (tin, tout) in costs:
            cost = {"usd_micros": 5, "input_tokens": tin, "output_tokens": tout}
            await c.execute(
                text("INSERT INTO effects (episode_id, key, kind, status, request_hash, cost) "
                     "VALUES ('e1', :k, 'llm', 'done', 'h', CAST(:c AS jsonb))"),
                {"k": key, "c": json.dumps(cost)},
            )  # fmt: skip
    await migrate(url, "upgrade", "0006")
    async with engine.connect() as c:
        rows = (
            await c.execute(
                text("SELECT id, latency_ms, tokens_in, tokens_out FROM episodes ORDER BY id")
            )
        ).all()
    # agent side only (agent_message + tool_result), simulator time excluded
    assert rows[0] == ("e1", 200, 150, 15)
    assert rows[1] == ("e2", None, None, None)  # unfinished episodes stay NULL
