"""Phase 5 tables: production conversations and their ingest counters (P5-1)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
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

__all__ = ["IngestStat", "ProdConversation", "ProdEvent", "ProdSpanSeen"]

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
