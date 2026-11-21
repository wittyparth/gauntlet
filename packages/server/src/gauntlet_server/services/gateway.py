"""Gateway decision ingest, stats and human approvals (P4-2, CQ-G2).

Approvals expire by the database clock: lazily on every read and by a worker sweep. An expired
approval is denied (the SDK acts on it as a block) and cannot be decided any more."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from gauntlet_core.gateway import DecisionRecord
from gauntlet_core.ids import new_id
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.policy_models import GatewayApprovalRow, GatewayDecisionRow
from ..deps import AppState
from ..errors import ApiError, not_found
from ..pagination import decode_cursor, encode_cursor
from .audit import audit

__all__ = [
    "AcceptedOut",
    "ApprovalIn",
    "ApprovalOut",
    "DecideIn",
    "DecisionsPage",
    "IngestIn",
    "StatsOut",
    "create_approval",
    "decide_approval",
    "expire_approvals",
    "expire_approvals_all",
    "gateway_stats",
    "get_approval",
    "ingest_decisions",
    "list_approvals",
    "list_decisions",
]

MAX_BATCH = 500
DEFAULT_EXPIRY_S = 900  # CQ-G2: 15 minutes
MAX_EXPIRY_S = 86_400
Status = Literal["pending", "approved", "denied", "expired"]


class IngestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    records: list[DecisionRecord] = Field(max_length=MAX_BATCH)


class AcceptedOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted: int
    duplicates: int


class DecisionsPage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[DecisionRecord]
    next_cursor: str | None


class RuleCount(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_id: str | None
    action: str
    count: int


class DayCount(RuleCount):
    day: str


class Overhead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    p50: float | None
    p95: float | None
    p99: float | None


class StatsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    window_s: int
    total: int
    by_action: dict[str, int]
    by_rule: list[RuleCount]
    by_day: list[DayCount]
    overhead_us: Overhead


class ApprovalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = Field(default=None, pattern=r"^gap_[A-Za-z0-9]{8,64}$")
    record: DecisionRecord
    expires_in_s: int = Field(default=DEFAULT_EXPIRY_S, ge=1, le=MAX_EXPIRY_S)


class ApprovalOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    status: Status
    decision: DecisionRecord
    requested_at: datetime
    expires_at: datetime
    decided_by: str | None
    decided_at: datetime | None
    note: str | None


class DecideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "deny"]
    note: str | None = Field(default=None, max_length=2000)


# -- decisions ----------------------------------------------------------------------------


def _row(ws: str, r: DecisionRecord) -> dict[str, Any]:
    return {
        "id": r.id, "workspace_id": ws, "ts": r.ts, "session_id": r.session_id,
        "agent_id": r.agent_id, "policy_id": r.policy_id, "policy_version": r.policy_version,
        "mode": r.mode, "kind": r.kind, "tool": r.tool, "action": r.action,
        "enforced": r.enforced, "rule_id": r.rule_id, "severity": r.severity,
        "overhead_us": r.overhead_us, "doc": r.model_dump(mode="json"),
    }  # fmt: skip


async def ingest_decisions(s: AsyncSession, ws: str, body: IngestIn) -> AcceptedOut:
    """Idempotent on the record id: a retried batch inserts nothing twice."""
    if not body.records:
        return AcceptedOut(accepted=0, duplicates=0)
    stmt = (
        insert(GatewayDecisionRow)
        .values([_row(ws, r) for r in body.records])
        .on_conflict_do_nothing(index_elements=["id"])
        .returning(GatewayDecisionRow.id)
    )
    inserted = len((await s.execute(stmt)).all())
    await s.commit()
    return AcceptedOut(accepted=inserted, duplicates=len(body.records) - inserted)


async def list_decisions(
    s: AsyncSession,
    ws: str,
    *,
    policy_id: str | None,
    action: str | None,
    tool: str | None,
    rule_id: str | None,
    mode: str | None,
    from_ts: datetime | None,
    to_ts: datetime | None,
    enforced: bool | None,
    limit: int,
    cursor: str | None,
) -> DecisionsPage:
    limit = max(1, min(limit, 200))
    q = select(GatewayDecisionRow).where(GatewayDecisionRow.workspace_id == ws)
    for col, val in (
        (GatewayDecisionRow.policy_id, policy_id),
        (GatewayDecisionRow.action, action),
        (GatewayDecisionRow.tool, tool),
        (GatewayDecisionRow.rule_id, rule_id),
        (GatewayDecisionRow.mode, mode),
        (GatewayDecisionRow.enforced, enforced),
    ):
        if val is not None:
            q = q.where(col == val)
    if from_ts is not None:
        q = q.where(GatewayDecisionRow.ts >= from_ts)
    if to_ts is not None:
        q = q.where(GatewayDecisionRow.ts <= to_ts)
    if cursor:
        ts, rid = decode_cursor(cursor)
        q = q.where(
            or_(
                GatewayDecisionRow.ts < ts,
                and_(GatewayDecisionRow.ts == ts, GatewayDecisionRow.id < rid),
            )
        )
    q = q.order_by(GatewayDecisionRow.ts.desc(), GatewayDecisionRow.id.desc()).limit(limit + 1)
    rows = list((await s.execute(q)).scalars())
    more = len(rows) > limit
    rows = rows[:limit]
    nxt = encode_cursor(rows[-1].ts, rows[-1].id) if more and rows else None
    return DecisionsPage(
        items=[DecisionRecord.model_validate(r.doc) for r in rows], next_cursor=nxt
    )


_WINDOW = re.compile(r"^(\d+)([smhd])$")
_UNIT = {"s": 1, "m": 60, "h": 3600, "d": 86_400}


def parse_window(window: str) -> int:
    m = _WINDOW.match(window)
    if m is None or int(m.group(1)) == 0:
        raise ApiError(422, "validation_error", "window looks like 30m, 1h or 7d")
    return min(int(m.group(1)) * _UNIT[m.group(2)], 90 * 86_400)


async def gateway_stats(s: AsyncSession, ws: str, window: str) -> StatsOut:
    secs = parse_window(window)
    since = datetime.now(UTC) - timedelta(seconds=secs)
    base = and_(GatewayDecisionRow.workspace_id == ws, GatewayDecisionRow.ts >= since)
    by_rule = (
        await s.execute(
            select(GatewayDecisionRow.rule_id, GatewayDecisionRow.action, func.count())
            .where(base)
            .group_by(GatewayDecisionRow.rule_id, GatewayDecisionRow.action)
            .order_by(func.count().desc(), GatewayDecisionRow.rule_id, GatewayDecisionRow.action)
        )
    ).all()
    day = func.to_char(func.timezone("UTC", GatewayDecisionRow.ts), "YYYY-MM-DD")
    by_day = (
        await s.execute(
            select(day, GatewayDecisionRow.rule_id, GatewayDecisionRow.action, func.count())
            .where(base, GatewayDecisionRow.rule_id.is_not(None))
            .group_by(day, GatewayDecisionRow.rule_id, GatewayDecisionRow.action)
            .order_by(day, GatewayDecisionRow.rule_id, GatewayDecisionRow.action)
        )
    ).all()
    pct = (
        await s.execute(
            select(
                func.percentile_cont(0.5).within_group(GatewayDecisionRow.overhead_us),
                func.percentile_cont(0.95).within_group(GatewayDecisionRow.overhead_us),
                func.percentile_cont(0.99).within_group(GatewayDecisionRow.overhead_us),
            ).where(base)
        )
    ).one()
    actions: dict[str, int] = {}
    for _, act, n in by_rule:
        actions[act] = actions.get(act, 0) + int(n)
    return StatsOut(
        window_s=secs,
        total=sum(actions.values()),
        by_action=actions,
        by_rule=[RuleCount(rule_id=r, action=a, count=int(n)) for r, a, n in by_rule],
        by_day=[DayCount(day=d, rule_id=r, action=a, count=int(n)) for d, r, a, n in by_day],
        overhead_us=Overhead(
            p50=None if pct[0] is None else float(pct[0]),
            p95=None if pct[1] is None else float(pct[1]),
            p99=None if pct[2] is None else float(pct[2]),
        ),
    )


# -- approvals ----------------------------------------------------------------------------


async def expire_approvals(s: AsyncSession, ws: str | None = None) -> int:
    """Mark pending approvals past their deadline `expired` (database clock)."""
    stmt = (
        update(GatewayApprovalRow)
        .where(GatewayApprovalRow.status == "pending", GatewayApprovalRow.expires_at < func.now())
        .values(status="expired")
    )
    if ws is not None:
        stmt = stmt.where(GatewayApprovalRow.workspace_id == ws)
    res = await s.execute(stmt)
    return int(res.rowcount or 0)  # type: ignore[attr-defined]


async def expire_approvals_all(state: AppState) -> int:
    """The worker sweep (every 30 s)."""
    async with state.sm() as s, s.begin():
        return await expire_approvals(s)


def _out(row: GatewayApprovalRow) -> ApprovalOut:
    return ApprovalOut(
        id=row.id,
        status=row.status,  # type: ignore[arg-type]
        decision=DecisionRecord.model_validate(row.decision_doc),
        requested_at=row.requested_at,
        expires_at=row.expires_at,
        decided_by=row.decided_by,
        decided_at=row.decided_at,
        note=row.note,
    )


async def create_approval(s: AsyncSession, ws: str, body: ApprovalIn, actor: str) -> ApprovalOut:
    """Idempotent on a client-supplied id (a retried request returns the same approval)."""
    aid = body.id or new_id("gap")
    existing = await s.get(GatewayApprovalRow, aid)
    if existing is not None:
        if existing.workspace_id != ws:
            raise ApiError(409, "conflict", "approval id is taken")
        await expire_approvals(s, ws)
        await s.commit()
        await s.refresh(existing)
        return _out(existing)
    expires = (
        await s.execute(select(func.now() + timedelta(seconds=body.expires_in_s)))
    ).scalar_one()
    row = GatewayApprovalRow(
        id=aid,
        workspace_id=ws,
        decision_doc=body.record.model_dump(mode="json"),
        status="pending",
        expires_at=expires,
    )
    s.add(row)
    await audit(
        s, ws, actor, "gateway.approval_requested", "approval", aid,
        {"policy_id": body.record.policy_id, "rule_id": body.record.rule_id,
         "tool": body.record.tool},
    )  # fmt: skip
    await s.commit()
    await s.refresh(row)
    return _out(row)


async def list_approvals(
    s: AsyncSession, ws: str, status: Status | None, limit: int
) -> list[ApprovalOut]:
    await expire_approvals(s, ws)
    await s.commit()
    q = select(GatewayApprovalRow).where(GatewayApprovalRow.workspace_id == ws)
    if status is not None:
        q = q.where(GatewayApprovalRow.status == status)
    q = q.order_by(GatewayApprovalRow.requested_at.desc(), GatewayApprovalRow.id.desc()).limit(
        max(1, min(limit, 200))
    )
    return [_out(r) for r in (await s.execute(q)).scalars()]


async def _owned(s: AsyncSession, ws: str, approval_id: str) -> GatewayApprovalRow:
    row = await s.get(GatewayApprovalRow, approval_id)
    if row is None or row.workspace_id != ws:
        raise not_found("approval", approval_id)
    return row


async def get_approval(s: AsyncSession, ws: str, approval_id: str) -> ApprovalOut:
    await _owned(s, ws, approval_id)
    await expire_approvals(s, ws)
    await s.commit()
    row = await _owned(s, ws, approval_id)
    await s.refresh(row)
    return _out(row)


async def decide_approval(
    s: AsyncSession, ws: str, approval_id: str, body: DecideIn, actor: str
) -> ApprovalOut:
    """Idempotent: repeating the same decision returns the decided approval; the opposite
    decision, or any decision on an expired approval, is a 409."""
    await _owned(s, ws, approval_id)
    await expire_approvals(s, ws)
    new_status = "approved" if body.decision == "approve" else "denied"
    won = (
        await s.execute(
            text(
                "UPDATE gateway_approvals SET status = :st, decided_by = :by, decided_at = now(), "
                "note = :note WHERE id = :id AND workspace_id = :ws AND status = 'pending' "
                "RETURNING id"
            ),
            {"st": new_status, "by": actor, "note": body.note, "id": approval_id, "ws": ws},
        )
    ).first()
    row = await _owned(s, ws, approval_id)
    await s.refresh(row)
    if won is None:
        await s.commit()
        if row.status == "expired":
            raise ApiError(409, "approval_expired", "the approval expired and cannot be decided")
        if row.status != new_status:
            raise ApiError(409, "conflict", f"the approval was already {row.status}")
        return _out(row)  # the same decision again
    doc = row.decision_doc
    await audit(
        s, ws, actor, "gateway.approval_decided", "approval", approval_id,
        {"decision": new_status, "policy_id": doc.get("policy_id"),
         "rule_id": doc.get("rule_id"), "tool": doc.get("tool")},
    )  # fmt: skip
    await s.commit()
    await s.refresh(row)
    return _out(row)
