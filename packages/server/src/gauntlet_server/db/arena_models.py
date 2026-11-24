"""Public challenge arena tables (P5-6). They live in the platform database under the `arena_`
prefix; the arena service (apps/arena) reads and writes them through its own database URL."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, created_at_col

__all__ = ["ArenaAttempt", "ArenaEvent", "ArenaHandle", "ArenaSolve"]


class ArenaHandle(Base):
    __tablename__ = "arena_handles"
    handle: Mapped[str] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = created_at_col()


class ArenaAttempt(Base):
    __tablename__ = "arena_attempts"
    __table_args__ = (
        CheckConstraint("status IN ('open','solved','failed','expired')", name="status"),
        CheckConstraint("level BETWEEN 1 AND 5", name="level"),
        Index("ix_arena_attempts_handle", "handle", text("started_at DESC")),
    )
    id: Mapped[str] = mapped_column(primary_key=True)  # arn_
    handle: Mapped[str] = mapped_column(ForeignKey("arena_handles.handle"))
    level: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(server_default="open")
    turns: Mapped[int] = mapped_column(Integer, server_default="0")
    started_at: Mapped[datetime] = created_at_col()
    solved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    canary_digest: Mapped[str]  # sha256 of the canary; the canary itself is never stored
    reported: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    spent_usd_micros: Mapped[int] = mapped_column(BigInteger, server_default="0")


class ArenaEvent(Base):
    __tablename__ = "arena_events"
    __table_args__ = (Index("ix_arena_events_created", "created_at"),)
    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("arena_attempts.id", ondelete="CASCADE"), primary_key=True
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str]
    doc: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()


class ArenaSolve(Base):
    __tablename__ = "arena_solves"
    __table_args__ = (Index("ix_arena_solves_level", "level", "turns", "seconds"),)
    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("arena_attempts.id", ondelete="CASCADE"), primary_key=True
    )
    handle: Mapped[str] = mapped_column(ForeignKey("arena_handles.handle"))
    level: Mapped[int] = mapped_column(Integer)
    turns: Mapped[int] = mapped_column(Integer)
    seconds: Mapped[int] = mapped_column(Integer)
