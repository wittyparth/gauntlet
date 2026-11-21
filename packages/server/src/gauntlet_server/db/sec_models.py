"""Phase 2 tables (CQ-S4): ownership verification, audit log, kill switches, findings, attacks."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, created_at_col, workspace_col

__all__ = [
    "Attack",
    "AuditLog",
    "EpisodeAttack",
    "Finding",
    "FindingEpisode",
    "KillSwitch",
    "TargetVerification",
]


def _ts() -> Mapped[datetime | None]:
    return mapped_column(DateTime(timezone=True))


class TargetVerification(Base):
    __tablename__ = "target_verifications"
    __table_args__ = (UniqueConstraint("workspace_id", "host"),)
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    host: Mapped[str]
    method: Mapped[str]
    token: Mapped[str]
    status: Mapped[str] = mapped_column(server_default="pending")
    verified_at: Mapped[datetime | None] = _ts()
    expires_at: Mapped[datetime | None] = _ts()
    last_checked_at: Mapped[datetime | None] = _ts()
    detail: Mapped[str | None]
    created_at: Mapped[datetime] = created_at_col()


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_ws", "workspace_id", "seq"),)
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor: Mapped[str]
    action: Mapped[str]
    subject_type: Mapped[str]
    subject_id: Mapped[str]
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    prev_hash: Mapped[str]
    hash: Mapped[str]
    seq: Mapped[int] = mapped_column(
        BigInteger, server_default=text("nextval('audit_log_seq_seq'::regclass)")
    )
    created_at: Mapped[datetime] = created_at_col()


class KillSwitch(Base):
    __tablename__ = "kill_switches"
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    scope: Mapped[str]
    run_id: Mapped[str | None]
    engaged_by: Mapped[str]
    reason: Mapped[str]
    engaged_at: Mapped[datetime] = created_at_col()
    released_at: Mapped[datetime | None] = _ts()
    created_at: Mapped[datetime] = created_at_col()


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        UniqueConstraint("workspace_id", "agent_version_id", "dedup_key"),
        Index("ix_findings_ws", "workspace_id", text("created_at DESC")),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    agent_version_id: Mapped[str] = mapped_column(ForeignKey("agent_versions.id"))
    category: Mapped[str]
    severity: Mapped[str]
    status: Mapped[str] = mapped_column(server_default="open")
    dedup_key: Mapped[str]
    title: Mapped[str]
    attack_id: Mapped[str | None]
    repro_successes: Mapped[int] = mapped_column(Integer, server_default="0")
    repro_attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    doc: Mapped[dict[str, Any]] = mapped_column(JSONB)
    notes: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = created_at_col()


class FindingEpisode(Base):
    __tablename__ = "finding_episodes"
    finding_id: Mapped[str] = mapped_column(ForeignKey("findings.id"), primary_key=True)
    episode_id: Mapped[str] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(server_default="evidence")
    evidence_seqs: Mapped[list[int]] = mapped_column(ARRAY(Integer), server_default="{}")
    created_at: Mapped[datetime] = created_at_col()


class Attack(Base):
    __tablename__ = "attacks"
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    doc: Mapped[dict[str, Any]] = mapped_column(JSONB)
    category: Mapped[str]
    vector: Mapped[str]
    source: Mapped[str]
    created_at: Mapped[datetime] = created_at_col()


class EpisodeAttack(Base):
    __tablename__ = "episode_attacks"
    __table_args__ = (Index("ix_episode_attacks_ws", "workspace_id", "category"),)
    episode_id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    attack_id: Mapped[str]
    category: Mapped[str]
    vector: Mapped[str]
    objective_held: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = created_at_col()
