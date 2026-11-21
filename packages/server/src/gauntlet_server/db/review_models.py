"""Phase 3 tables: human labels, calibrations, the generic jobs table (P3-5)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, created_at_col, workspace_col

__all__ = ["BadgeToken", "Calibration", "HumanLabel", "Job"]

_EMPTY_OBJ = text("'{}'::jsonb")


class HumanLabel(Base):
    __tablename__ = "human_labels"
    __table_args__ = (
        CheckConstraint("result IN ('pass','fail','na')", name="result"),
        UniqueConstraint("episode_id", "rubric_id", "labeler"),
        Index("ix_human_labels_ws", "workspace_id", "rubric_id"),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id"))
    rubric_id: Mapped[str]
    rubric_version: Mapped[int | None] = mapped_column(Integer)
    result: Mapped[str]
    labeler: Mapped[str]
    note: Mapped[str | None]
    is_golden: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = created_at_col()


class Calibration(Base):
    __tablename__ = "calibrations"
    __table_args__ = (
        CheckConstraint("status IN ('queued','running','done','failed')", name="status"),
        Index("ix_calibrations_rubric", "workspace_id", "rubric_id", text("created_at DESC")),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    rubric_id: Mapped[str]
    rubric_version: Mapped[int] = mapped_column(Integer)
    judge_models: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=_EMPTY_OBJ)
    status: Mapped[str] = mapped_column(server_default="queued")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    golden_count: Mapped[int] = mapped_column(Integer, server_default="0")
    gating_allowed: Mapped[bool] = mapped_column(Boolean, server_default="false")
    threshold: Mapped[float | None] = mapped_column(Float)
    stale: Mapped[bool] = mapped_column(Boolean, server_default="false")
    error: Mapped[str | None]
    cost_usd_micros: Mapped[int] = mapped_column(BigInteger, server_default="0")
    created_at: Mapped[datetime] = created_at_col()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("status IN ('queued','running','done','failed')", name="status"),
        Index(
            "ix_jobs_claim", "created_at", postgresql_where=text("status IN ('queued','running')")
        ),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    kind: Mapped[str]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=_EMPTY_OBJ)
    status: Mapped[str] = mapped_column(server_default="queued")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None]
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    lease_owner: Mapped[str | None]
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    not_before: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    created_at: Mapped[datetime] = created_at_col()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BadgeToken(Base):
    __tablename__ = "badge_tokens"
    __table_args__ = (UniqueConstraint("token"), Index("ix_badge_tokens_agent", "agent_id"))
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    token: Mapped[str]
    created_at: Mapped[datetime] = created_at_col()
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
