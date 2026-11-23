"""Scheduled runs (P5-7): a minimal five-field cron in UTC, a worker tick with an injectable
clock, and a compare-and-set claim so one tick fires a schedule once even with several workers.

Fields: minute hour day-of-month month day-of-week (0 or 7 = Sunday). Each field takes `*`,
`*/n`, `a`, `a-b`, `a-b/n` and comma lists. When both day fields are restricted a day matches
if either does (the usual cron rule). Nothing is scheduled by default. Every fire goes through
`create_run` (the budget ledger, the daily cap and the kill switches apply); a refused budget is
recorded as `skipped_budget`, not retried."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from gauntlet_core.ids import new_id
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import AgentVersion, Suite
from ..db.ops_models import Schedule
from ..deps import AppState
from ..errors import ApiError, not_found
from .audit import audit
from .runs import RunCreate, create_run

__all__ = [
    "FireOut",
    "ScheduleIn",
    "ScheduleOut",
    "SchedulePatch",
    "create_schedule",
    "delete_schedule",
    "fire_now",
    "list_schedules",
    "next_fire",
    "parse_cron",
    "tick",
    "update_schedule",
]

log = logging.getLogger("gauntlet.schedules")

_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
_HORIZON = timedelta(days=366 * 5)


class CronError(ValueError):
    pass


def _field(spec: str, lo: int, hi: int) -> frozenset[int]:
    out: set[int] = set()
    for part in spec.split(","):
        base, _, step_s = part.partition("/")
        try:
            step = int(step_s) if step_s else 1
            if step < 1:
                raise ValueError
            if base == "*":
                a, b = lo, hi
            elif "-" in base:
                x, y = base.split("-", 1)
                a, b = int(x), int(y)
            else:
                a = int(base)
                b = hi if step_s else a
        except ValueError as e:
            raise CronError(f"bad cron field {spec!r}") from e
        if a < lo or b > hi or a > b:
            raise CronError(f"cron field {spec!r} out of range {lo}-{hi}")
        out.update(range(a, b + 1, step))
    return frozenset(out)


@dataclass(frozen=True)
class CronSpec:
    minute: frozenset[int]
    hour: frozenset[int]
    dom: frozenset[int]
    month: frozenset[int]
    dow: frozenset[int]  # 0 = Sunday
    dom_star: bool
    dow_star: bool

    def day_ok(self, d: datetime) -> bool:
        dom, dow = d.day in self.dom, (d.isoweekday() % 7) in self.dow
        if self.dom_star and self.dow_star:
            return True
        if self.dom_star:
            return dow
        if self.dow_star:
            return dom
        return dom or dow  # both restricted: either matches


def parse_cron(expr: str) -> CronSpec:
    parts = expr.split()
    if len(parts) != 5:
        raise CronError("cron needs five fields: minute hour day-of-month month day-of-week")
    f = [_field(p, lo, hi) for p, (lo, hi) in zip(parts, _RANGES, strict=True)]
    return CronSpec(
        f[0], f[1], f[2], f[3], frozenset(d % 7 for d in f[4]),
        parts[2].startswith("*"), parts[4].startswith("*"),
    )  # fmt: skip


def next_fire(expr: str, after: datetime) -> datetime:
    """The first matching minute strictly after `after` (UTC)."""
    spec = parse_cron(expr)
    t = after.astimezone(UTC).replace(second=0, microsecond=0) + timedelta(minutes=1)
    limit = t + _HORIZON
    while t < limit:
        if t.month not in spec.month or not spec.day_ok(t):
            t = (t + timedelta(days=1)).replace(hour=0, minute=0)
            continue
        if t.hour not in spec.hour:
            t = (t + timedelta(hours=1)).replace(minute=0)
            continue
        if t.minute not in spec.minute:
            t += timedelta(minutes=1)
            continue
        return t
    raise CronError("cron expression never fires")


# --------------------------------------------------------------------------- API models


class ScheduleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_version_id: str
    suite_id: str
    cron: str
    timezone: Literal["UTC"] = "UTC"  # UTC only in v1 (CQ-P9)
    budget_usd_micros: int = Field(gt=0)
    enabled: bool = True


class SchedulePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cron: str | None = None
    budget_usd_micros: int | None = Field(default=None, gt=0)
    enabled: bool | None = None


class ScheduleOut(BaseModel):
    id: str
    agent_version_id: str
    suite_id: str
    cron: str
    timezone: str
    budget_usd_micros: int
    enabled: bool
    last_fired_at: datetime | None
    next_fire_at: datetime | None
    last_run_id: str | None
    last_status: str | None
    skipped_budget: int
    created_at: datetime


class FireOut(BaseModel):
    schedule_id: str
    status: Literal["fired", "skipped_budget", "error"]
    run_id: str | None = None
    detail: str | None = None


def _out(r: Schedule) -> ScheduleOut:
    return ScheduleOut.model_validate(r, from_attributes=True)


def _checked(expr: str) -> str:
    try:
        parse_cron(expr)
        next_fire(expr, datetime.now(UTC))
    except CronError as e:
        raise ApiError(422, "bad_cron", str(e)) from e
    return expr


async def _owned(s: AsyncSession, ws: str, sid: str) -> Schedule:
    row = await s.get(Schedule, sid)
    if row is None or row.workspace_id != ws:
        raise not_found("schedule", sid)
    return row


async def create_schedule(
    s: AsyncSession, ws: str, body: ScheduleIn, actor: str, now: datetime | None = None
) -> ScheduleOut:
    now = now or datetime.now(UTC)
    _checked(body.cron)
    av = await s.get(AgentVersion, body.agent_version_id)
    if av is None or av.workspace_id != ws:
        raise not_found("agent version", body.agent_version_id)
    suite = await s.get(Suite, body.suite_id)
    if suite is None or suite.workspace_id != ws:
        raise not_found("suite", body.suite_id)
    row = Schedule(
        id=new_id("sch"), workspace_id=ws, agent_version_id=av.id, suite_id=suite.id,
        cron=body.cron, timezone="UTC", budget_usd_micros=body.budget_usd_micros,
        enabled=body.enabled, next_fire_at=next_fire(body.cron, now) if body.enabled else None,
    )  # fmt: skip
    s.add(row)
    await audit(s, ws, actor, "schedule.create", "schedule", row.id,
                {"suite_id": suite.id, "agent_version_id": av.id, "cron": body.cron})  # fmt: skip
    await s.commit()
    await s.refresh(row)
    return _out(row)


async def list_schedules(s: AsyncSession, ws: str) -> list[ScheduleOut]:
    rows = (
        await s.execute(
            select(Schedule).where(Schedule.workspace_id == ws).order_by(Schedule.created_at)
        )
    ).scalars()
    return [_out(r) for r in rows]


async def update_schedule(
    s: AsyncSession, ws: str, sid: str, body: SchedulePatch, actor: str, now: datetime | None = None
) -> ScheduleOut:
    now = now or datetime.now(UTC)
    row = await _owned(s, ws, sid)
    if body.cron is not None:
        row.cron = _checked(body.cron)
    if body.budget_usd_micros is not None:
        row.budget_usd_micros = body.budget_usd_micros
    if body.enabled is not None:
        row.enabled = body.enabled
    row.next_fire_at = next_fire(row.cron, now) if row.enabled else None
    await audit(s, ws, actor, "schedule.update", "schedule", sid,
                {"fields": sorted(body.model_fields_set)})  # fmt: skip
    await s.commit()
    await s.refresh(row)
    return _out(row)


async def delete_schedule(s: AsyncSession, ws: str, sid: str, actor: str) -> None:
    row = await _owned(s, ws, sid)
    await s.delete(row)
    await audit(s, ws, actor, "schedule.delete", "schedule", sid, {})
    await s.commit()


# --------------------------------------------------------------------------- firing


async def _fire(state: AppState, row_id: str, actor: str) -> FireOut:
    """Create the run for a schedule that has already been claimed (or is run on demand)."""
    status: Literal["fired", "skipped_budget", "error"] = "fired"
    run_id: str | None = None
    detail: str | None = None
    async with state.sm() as s:
        row = await s.get(Schedule, row_id)
        assert row is not None
        body = RunCreate(
            suite_id=row.suite_id, agent_version_id=row.agent_version_id,
            budget_usd_micros=row.budget_usd_micros,
        )  # fmt: skip
        try:
            out, _ = await create_run(s, state, row.workspace_id, body, actor=actor)
            await s.commit()
            run_id = str(out["id"])
        except ApiError as e:
            await s.rollback()
            status = "skipped_budget" if "budget" in e.code else "error"
            detail = e.code
    async with state.sm() as s, s.begin():
        row = await s.get(Schedule, row_id)
        assert row is not None
        row.last_status = status
        if run_id:
            row.last_run_id = run_id
        if status == "skipped_budget":
            row.skipped_budget += 1
    return FireOut(schedule_id=row_id, status=status, run_id=run_id, detail=detail)


async def fire_now(state: AppState, ws: str, sid: str, actor: str) -> FireOut:
    """`run-now`: audited, goes through the same budget checks, does not move `next_fire_at`."""
    async with state.sm() as s:
        row = await _owned(s, ws, sid)
        await audit(s, ws, actor, "schedule.run_now", "schedule", row.id, {})
        await s.commit()
    return await _fire(state, sid, actor)


async def tick(
    state: AppState, now: datetime | Callable[[], datetime] | None = None
) -> list[FireOut]:
    """Fire every due schedule once. The claim is an UPDATE guarded on the `next_fire_at` we
    read, so of several workers racing for the same schedule exactly one gets rowcount 1."""
    t = now() if callable(now) else (now or datetime.now(UTC))
    fired: list[FireOut] = []
    async with state.sm() as s:
        due = (
            await s.execute(
                select(Schedule.id, Schedule.cron, Schedule.next_fire_at).where(
                    Schedule.enabled.is_(True), Schedule.next_fire_at <= t
                )
            )
        ).all()
    for sid, cron, seen in due:
        try:
            nxt = next_fire(cron, t)
        except CronError:
            continue
        async with state.sm() as s, s.begin():
            res = await s.execute(
                update(Schedule)
                .where(
                    Schedule.id == sid, Schedule.enabled.is_(True), Schedule.next_fire_at == seen
                )
                .values(next_fire_at=nxt, last_fired_at=t)
            )
            won = res.rowcount == 1  # type: ignore[attr-defined]
        if won:
            fired.append(await _fire(state, sid, f"schedule:{sid}"))
    return fired
