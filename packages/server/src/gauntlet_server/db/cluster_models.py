"""Failure clustering tables (P3-6)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from sqlalchemy import Float, ForeignKey, Index, Integer, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, created_at_col

__all__ = ["FailureCluster", "FailureEmbedding"]

EMBED_DIM = 1536


class FailureEmbedding(Base):
    __tablename__ = "failure_embeddings"
    __table_args__ = (Index("ix_failure_embeddings_run", "run_id"),)
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id"), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    embedding: Mapped[Any] = mapped_column(Vector(EMBED_DIM))
    text_hash: Mapped[str]


class FailureCluster(Base):
    __tablename__ = "failure_clusters"
    __table_args__ = (Index("ix_failure_clusters_run", "run_id", "label"),)
    id: Mapped[str] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    label: Mapped[int] = mapped_column(Integer)
    name: Mapped[str]
    description: Mapped[str] = mapped_column(server_default="")
    suspected_cause: Mapped[str] = mapped_column(server_default="")
    root_cause: Mapped[str]
    root_cause_share: Mapped[float] = mapped_column(Float)
    max_severity: Mapped[str | None]
    member_episode_ids: Mapped[list[Any]] = mapped_column(JSONB)
    scenario_ids: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    exemplar_episode_id: Mapped[str | None]
    created_at: Mapped[datetime] = created_at_col()
