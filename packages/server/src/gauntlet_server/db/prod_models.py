"""Phase 5 tables: production conversations and their ingest counters (P5-1)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
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

__all__ = [
    "IngestStat",
    "MiningCandidate",
    "MiningRun",
    "ProdConversation",
    "ProdEvent",
    "ProdSpanSeen",
]

_EMPTY = text("'{}'::jsonb")


class ProdConversation(Base):
    __tablename__ = "prod_conversations"
    __table_args__ = (
        UniqueConstraint("workspace_id", "external_session_id"),
        Index("ix_prod_conversations_ws", "workspace_id", text("started_at DESC")),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"))
    external_session_id: Mapped[str]
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_count: Mapped[int] = mapped_column(Integer, server_default="0")
    signals: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=_EMPTY)
    redaction: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=_EMPTY)
    run_id: Mapped[str | None]
    created_at: Mapped[datetime] = created_at_col()


class ProdEvent(Base):
    __tablename__ = "prod_events"
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("prod_conversations.id", ondelete="CASCADE"), primary_key=True
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str]
    doc: Mapped[dict[str, Any]] = mapped_column(JSONB)


class ProdSpanSeen(Base):
    __tablename__ = "prod_spans_seen"
    __table_args__ = (Index("ix_prod_spans_seen_created", "created_at"),)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), primary_key=True)
    trace_id: Mapped[str] = mapped_column(primary_key=True)
    span_id: Mapped[str] = mapped_column(primary_key=True)
    conversation_id: Mapped[str | None]  # which conversation the span went into
    created_at: Mapped[datetime] = created_at_col()


class IngestStat(Base):
    __tablename__ = "ingest_stats"
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    spans: Mapped[int] = mapped_column(BigInteger, server_default="0")
    bytes: Mapped[int] = mapped_column(BigInteger, server_default="0")
    rejected: Mapped[int] = mapped_column(BigInteger, server_default="0")
    redactions: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=_EMPTY)


class MiningRun(Base):
    __tablename__ = "mining_runs"
    __table_args__ = (
        CheckConstraint("status IN ('queued','running','done','failed')", name="status"),
        Index("ix_mining_runs_ws", "workspace_id", text("created_at DESC")),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    window: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(server_default="queued")
    counts: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=_EMPTY)
    budget_usd_micros: Mapped[int] = mapped_column(BigInteger)
    spent_usd_micros: Mapped[int] = mapped_column(BigInteger, server_default="0")
    error: Mapped[str | None]
    created_at: Mapped[datetime] = created_at_col()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MiningCandidate(Base):
    __tablename__ = "mining_candidates"
    __table_args__ = (
        UniqueConstraint("mining_run_id", "conversation_id"),
        CheckConstraint("status IN ('new','converted','dismissed')", name="status"),
        Index("ix_mining_candidates_run", "mining_run_id", text("score DESC")),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    mining_run_id: Mapped[str] = mapped_column(ForeignKey("mining_runs.id", ondelete="CASCADE"))
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("prod_conversations.id", ondelete="CASCADE")
    )
    score: Mapped[float] = mapped_column(Float)
    parts: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reasons: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    detector_hits: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    cluster_id: Mapped[str | None]
    cluster_name: Mapped[str | None]
    status: Mapped[str] = mapped_column(server_default="new")
    dismissed_reason: Mapped[str | None]
    scenario_id: Mapped[str | None]
    convert_error: Mapped[str | None]
    created_at: Mapped[datetime] = created_at_col()
