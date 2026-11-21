"""Phase 4 tables: policies and their review proposals (P4-1), gateway decisions and
approvals (P4-2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, created_at_col, workspace_col

__all__ = ["PolicyProposalRow", "PolicyVersion"]


class PolicyVersion(Base):
    """One immutable (published) or editable (draft) version of a policy. `doc` is a `Policy`."""

    __tablename__ = "policies"
    __table_args__ = (
        CheckConstraint("status IN ('draft','published')", name="status"),
        Index("ix_policies_ws", "workspace_id", "id"),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    name: Mapped[str]
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"))
    doc: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str]
    source_text: Mapped[str]
    created_at: Mapped[datetime] = created_at_col()


class PolicyProposalRow(Base):
    """The compiled proposals of one policy version. `doc` is a `CompiledPolicy`."""

    __tablename__ = "policy_proposals"
    __table_args__ = (UniqueConstraint("policy_id", "version"),)
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    policy_id: Mapped[str]
    version: Mapped[int] = mapped_column(Integer)
    doc: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()
