"""Phase 4 tables: policies and their review proposals (P4-1), gateway decisions and
approvals (P4-2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, created_at_col, workspace_col

__all__ = ["GatewayApprovalRow", "GatewayDecisionRow", "PolicyProposalRow", "PolicyVersion"]


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


class GatewayDecisionRow(Base):
    """One gateway decision. `doc` is the full `DecisionRecord`; the columns are for filters."""

    __tablename__ = "gateway_decisions"
    __table_args__ = (
        CheckConstraint("mode IN ('shadow','enforce')", name="mode"),
        CheckConstraint("kind IN ('tool_call','output')", name="kind"),
        CheckConstraint(
            "action IN ('allow','block','require_approval','redact','log')", name="action"
        ),
        Index("ix_gateway_decisions_ws_ts", "workspace_id", text("ts DESC"), text("id DESC")),
        Index("ix_gateway_decisions_policy", "workspace_id", "policy_id", "ts"),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    session_id: Mapped[str]
    agent_id: Mapped[str | None]
    policy_id: Mapped[str]
    policy_version: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str]
    kind: Mapped[str]
    tool: Mapped[str | None]
    action: Mapped[str]
    enforced: Mapped[bool] = mapped_column(Boolean)
    rule_id: Mapped[str | None]
    severity: Mapped[str | None]
    overhead_us: Mapped[int] = mapped_column(Integer)
    doc: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()


class GatewayApprovalRow(Base):
    __tablename__ = "gateway_approvals"
    __table_args__ = (
        CheckConstraint("status IN ('pending','approved','denied','expired')", name="status"),
        Index("ix_gateway_approvals_ws_status", "workspace_id", "status"),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    decision_doc: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str]
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[str | None]
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None]
    created_at: Mapped[datetime] = created_at_col()
