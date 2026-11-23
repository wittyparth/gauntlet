"""Phase 5 operations tables: schedules, SLOs, alert channels, rules and alerts, evidence
packs (P5-7)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
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

__all__ = ["Alert", "AlertChannel", "AlertRule", "EvidencePack", "Schedule", "Slo"]

_EMPTY_ARR = text("'[]'::jsonb")
_EMPTY = text("'{}'::jsonb")


class Schedule(Base):
    __tablename__ = "schedules"
    __table_args__ = (Index("ix_schedules_due", "enabled", "next_fire_at"),)
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    agent_version_id: Mapped[str] = mapped_column(ForeignKey("agent_versions.id"))
    suite_id: Mapped[str] = mapped_column(ForeignKey("suites.id"))
    cron: Mapped[str]
    timezone: Mapped[str] = mapped_column(server_default="UTC")
    budget_usd_micros: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_fire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_id: Mapped[str | None]
    last_status: Mapped[str | None]
    skipped_budget: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = created_at_col()


class Slo(Base):
    __tablename__ = "slos"
    __table_args__ = (
        CheckConstraint(
            "metric IN ('pass_rate','attack_success_rate','latency_p95',"
            "'cost_per_episode','prod_failure_rate')",
            name="metric",
        ),
        Index("ix_slos_ws", "workspace_id", "agent_id"),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    metric: Mapped[str]
    objective: Mapped[float] = mapped_column(Float)
    window_days: Mapped[int] = mapped_column(Integer)
    burn_alerts: Mapped[list[Any]] = mapped_column(JSONB, server_default=_EMPTY_ARR)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = created_at_col()


class AlertChannel(Base):
    __tablename__ = "alert_channels"
    __table_args__ = (
        CheckConstraint("kind IN ('webhook','slack','email')", name="kind"),
        Index("ix_alert_channels_ws", "workspace_id"),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    kind: Mapped[str]
    secret_name: Mapped[str]
    created_at: Mapped[datetime] = created_at_col()


class AlertRule(Base):
    __tablename__ = "alert_rules"
    __table_args__ = (
        CheckConstraint("kind IN ('burn','breach','finding','gateway_block_rate')", name="kind"),
        Index("ix_alert_rules_ws", "workspace_id"),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    slo_id: Mapped[str | None] = mapped_column(ForeignKey("slos.id", ondelete="CASCADE"))
    kind: Mapped[str]
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=_EMPTY)
    channel_ids: Mapped[list[Any]] = mapped_column(JSONB, server_default=_EMPTY_ARR)
    silence_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("rule_id", "fingerprint"),
        CheckConstraint("state IN ('firing','resolved')", name="state"),
        Index("ix_alerts_ws", "workspace_id", "state"),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    rule_id: Mapped[str] = mapped_column(ForeignKey("alert_rules.id", ondelete="CASCADE"))
    fingerprint: Mapped[str]
    state: Mapped[str]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=_EMPTY)
    first_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notified_state: Mapped[str | None]


class EvidencePack(Base):
    __tablename__ = "evidence_packs"
    __table_args__ = (
        CheckConstraint("status IN ('queued','running','done','failed')", name="status"),
        Index("ix_evidence_packs_ws", "workspace_id", text("created_at DESC")),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = workspace_col()
    agent_version_id: Mapped[str] = mapped_column(ForeignKey("agent_versions.id"))
    frameworks: Mapped[list[Any]] = mapped_column(JSONB, server_default=_EMPTY_ARR)
    status: Mapped[str] = mapped_column(server_default="queued")
    object_key: Mapped[str | None]
    sha256: Mapped[str | None]
    signed: Mapped[bool] = mapped_column(Boolean, server_default="false")
    error: Mapped[str | None]
    created_at: Mapped[datetime] = created_at_col()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
