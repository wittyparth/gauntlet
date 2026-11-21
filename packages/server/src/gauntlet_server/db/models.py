"""Tables of contracts section 8 (up to `verdicts` and `secrets`) plus the attempt archives.

Conventions: text ids from `gauntlet_core.ids.new_id`, never database generated; versioned
document tables key on (id, version); JSON columns are JSONB holding the Pydantic models.
`events`, `effects`, the archives and `suite_scenarios` are children of an episode or suite
and carry no `workspace_id` of their own (the parent has it).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, created_at_col, workspace_col

__all__ = [
    "Agent",
    "AgentVersion",
    "ApiKey",
    "Effect",
    "EffectArchive",
    "Episode",
    "Event",
    "EventArchive",
    "Persona",
    "Project",
    "Rubric",
    "Run",
    "Scenario",
    "Secret",
    "Suite",
    "SuiteScenario",
    "Verdict",
    "Workspace",
    "WorkspaceSettings",
    "World",
]

_EMPTY_OBJ = text("'{}'::jsonb")
_EMPTY_ARR = text("'[]'::jsonb")


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    created_at: Mapped[datetime] = created_at_col()


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    hash: Mapped[str] = mapped_column(unique=True)
    prefix: Mapped[str | None]
    name: Mapped[str | None]
    scopes: Mapped[list[Any]] = mapped_column(JSONB, server_default=_EMPTY_ARR)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    name: Mapped[str]
    created_at: Mapped[datetime] = created_at_col()


class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str]
    created_at: Mapped[datetime] = created_at_col()


class AgentVersion(Base):
    __tablename__ = "agent_versions"
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    label: Mapped[str]
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    world_id: Mapped[str | None]  # CQ-B16: the world the agent's tools come from
    created_at: Mapped[datetime] = created_at_col()


class _Versioned:
    """(id, version) keyed document table."""

    id: Mapped[str] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)


class Persona(_Versioned, Base):
    __tablename__ = "personas"
    workspace_id: Mapped[str] = workspace_col()
    doc: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()


class World(_Versioned, Base):
    __tablename__ = "worlds"
    workspace_id: Mapped[str] = workspace_col()
    doc: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()


class Rubric(_Versioned, Base):
    __tablename__ = "rubrics"
    workspace_id: Mapped[str] = workspace_col()
    doc: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()


class Scenario(_Versioned, Base):
    __tablename__ = "scenarios"
    __table_args__ = (
        CheckConstraint("status IN ('draft','approved')", name="status"),
        CheckConstraint("source IN ('pack','generated','mined','pinned')", name="source"),
    )
    workspace_id: Mapped[str] = workspace_col()
    doc: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(server_default="draft")
    source: Mapped[str] = mapped_column(server_default="pack")
    quarantined: Mapped[bool] = mapped_column(server_default="false")
    quarantine_reason: Mapped[str | None] = mapped_column(Text)
    quarantined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()


class Suite(Base):
    __tablename__ = "suites"
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    name: Mapped[str]
    repetitions: Mapped[int] = mapped_column(Integer, server_default="1")
    persona_mix: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()


class SuiteScenario(Base):
    __tablename__ = "suite_scenarios"
    suite_id: Mapped[str] = mapped_column(ForeignKey("suites.id"), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(primary_key=True)
    position: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = created_at_col()


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(
            "reserved_usd_micros >= 0 AND spent_usd_micros >= 0 AND budget_usd_micros >= 0",
            name="budget_nonneg",
        ),
        CheckConstraint(
            "status IN ('queued','running','paused','cancelled','done','failed')", name="status"
        ),
        Index("ix_runs_ws", "workspace_id", text("created_at DESC")),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    suite_id: Mapped[str] = mapped_column(ForeignKey("suites.id"))
    agent_version_id: Mapped[str] = mapped_column(ForeignKey("agent_versions.id"))
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(server_default="queued")
    repetitions: Mapped[int] = mapped_column(Integer, server_default="1")
    seed: Mapped[int] = mapped_column(BigInteger, server_default="0")
    world_versions: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=_EMPTY_OBJ)
    budget_usd_micros: Mapped[int] = mapped_column(BigInteger)
    reserved_usd_micros: Mapped[int] = mapped_column(BigInteger, server_default="0")
    spent_usd_micros: Mapped[int] = mapped_column(BigInteger, server_default="0")
    # resolved {role: {model, reasoning}} the run's worker must use (null: process defaults)
    role_settings: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    baseline_of: Mapped[str | None] = mapped_column(ForeignKey("runs.id"))
    purpose: Mapped[str] = mapped_column(server_default="eval")
    finding_id: Mapped[str | None]
    attack: Mapped[bool] = mapped_column(server_default="false")  # placed attack scenarios inside
    adaptive: Mapped[bool] = mapped_column(server_default="false")  # sequential stopping (P3-2)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()


class Episode(Base):
    __tablename__ = "episodes"
    __table_args__ = (
        CheckConstraint("status IN ('queued','leased','done','cancelled')", name="status"),
        Index(
            "ix_episodes_claim",
            "priority",
            "created_at",
            postgresql_where=text("status IN ('queued','leased')"),
        ),
        Index("ix_episodes_run", "run_id", "status"),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    scenario_id: Mapped[str]
    scenario_version: Mapped[int | None] = mapped_column(Integer)
    rep: Mapped[int] = mapped_column(Integer, server_default="0")
    status: Mapped[str] = mapped_column(server_default="queued")
    outcome: Mapped[str | None]
    termination: Mapped[str | None]
    epoch: Mapped[int] = mapped_column(Integer, server_default="0")
    lease_owner: Mapped[str | None]
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt: Mapped[int] = mapped_column(Integer, server_default="0")
    next_seq: Mapped[int] = mapped_column(Integer, server_default="0")
    cost_usd_micros: Mapped[int] = mapped_column(BigInteger, server_default="0")
    not_before: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    priority: Mapped[int] = mapped_column(Integer, server_default="0")
    rng_seed: Mapped[int] = mapped_column(BigInteger, server_default="0")
    world_fidelity: Mapped[str] = mapped_column(server_default="full")
    latency_ms: Mapped[int | None] = mapped_column(Integer)  # agent-side time, set at finish
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()


class Event(Base):
    __tablename__ = "events"
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id"), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str]
    doc: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()


class Effect(Base):
    __tablename__ = "effects"
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id"), primary_key=True)
    key: Mapped[str] = mapped_column(primary_key=True)
    kind: Mapped[str]
    status: Mapped[str]
    request_hash: Mapped[str]
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    cost: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    span: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()


class EventArchive(Base):
    __tablename__ = "events_archive"
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id"), primary_key=True)
    attempt: Mapped[int] = mapped_column(Integer, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str]
    doc: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()


class EffectArchive(Base):
    __tablename__ = "effects_archive"
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id"), primary_key=True)
    attempt: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(primary_key=True)
    kind: Mapped[str]
    status: Mapped[str]
    request_hash: Mapped[str]
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    cost: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    span: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()


class Verdict(Base):
    __tablename__ = "verdicts"
    __table_args__ = (Index("ix_verdicts_episode", "episode_id"),)
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id"))
    evaluator: Mapped[str]
    criterion: Mapped[str]
    result: Mapped[str]
    doc: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()


class Secret(Base):
    __tablename__ = "secrets"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_secrets_workspace_id_name"),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    name: Mapped[str]
    ciphertext: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()


class WorkspaceSettings(Base):
    __tablename__ = "workspace_settings"
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), primary_key=True)
    # {role: {model, reasoning}} chosen by the workspace; absent roles use the defaults
    model_roles: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=_EMPTY_OBJ)
    # attack_scope, auto_pin_on_fixed (security controls, P2-4)
    doc: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=_EMPTY_OBJ)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )


from . import cluster_models, review_models, sec_models  # noqa: E402,F401  (Phase 2 and 3 tables)
