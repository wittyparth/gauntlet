"""Service-level objectives over stored runs and production signals (P5-7).

Objective semantics per metric (documented in the API field description):
- `pass_rate`: minimum pass rate of eval episodes (0 < x <= 1).
- `attack_success_rate`, `prod_failure_rate`: maximum allowed rate (0 <= x < 1); zero tolerates
  no bad event at all.
- `latency_p95` (ms), `cost_per_episode` (usd micros): maximum value at the 95th percentile,
  i.e. at least 95 percent of episodes must be at or under the objective.

Internally every metric becomes good-or-bad samples and `slo_status` of the core module judges
them: a breach needs the interval to exclude the objective."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from gauntlet_core.ids import new_id
from gauntlet_core.slo import Sample, SloStatus, burn_alerts, slo_status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import models as m
from ..db.ops_models import Slo
from ..db.prod_models import ProdConversation
from ..errors import ApiError, not_found
from .audit import audit

__all__ = [
    "SloIn",
    "SloOut",
    "SloPatch",
    "SloStatusOut",
    "create_slo",
    "delete_slo",
    "evaluate_slo",
    "get_slo",
    "list_slos",
    "slo_status_out",
    "update_slo",
]

Metric = Literal[
    "pass_rate", "attack_success_rate", "latency_p95", "cost_per_episode", "prod_failure_rate"
]
P95 = 0.95
MAX_SAMPLES = 20_000


def _check_objective(metric: str, objective: float) -> None:
    ok = {
        "pass_rate": 0 < objective <= 1,
        "attack_success_rate": 0 <= objective < 1,
        "prod_failure_rate": 0 <= objective < 1,
        "latency_p95": objective > 0,
        "cost_per_episode": objective > 0,
    }[metric]
    if not ok:
        raise ApiError(422, "bad_objective", f"objective {objective} is invalid for {metric}")


class SloIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_id: str
    metric: Metric
    objective: float = Field(description="see the module notes: a minimum or a maximum per metric")
    window_days: int = Field(default=30, ge=1, le=365)
    burn_alerts: list[Literal["fast", "slow"]] = Field(default_factory=lambda: ["fast", "slow"])
    enabled: bool = True

    @model_validator(mode="after")
    def _obj(self) -> SloIn:
        _check_objective(self.metric, self.objective)
        return self


class SloPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    objective: float | None = None
    window_days: int | None = Field(default=None, ge=1, le=365)
    burn_alerts: list[Literal["fast", "slow"]] | None = None
    enabled: bool | None = None


class SloOut(BaseModel):
    id: str
    agent_id: str
    metric: str
    objective: float
    window_days: int
    burn_alerts: list[str]
    enabled: bool
    created_at: datetime


class SloStatusOut(BaseModel):
    slo_id: str
    metric: str
    objective: float
    state: Literal["ok", "warning", "breached", "unknown"]
    n: int
    value: float | None  # the metric on its own scale (a pass rate, an attack rate, a p95 bound)
    interval: tuple[float, float] | None
    error_budget_remaining: float | None
    burn_rates: dict[str, float]
    firing_burn_alerts: list[str]
    breached: bool
    warning: bool
    window_days: int


def _out(r: Slo) -> SloOut:
    return SloOut.model_validate(r, from_attributes=True)


async def _owned(s: AsyncSession, ws: str, slo_id: str) -> Slo:
    row = await s.get(Slo, slo_id)
    if row is None or row.workspace_id != ws:
        raise not_found("slo", slo_id)
    return row


async def create_slo(s: AsyncSession, ws: str, body: SloIn, actor: str) -> SloOut:
    agent = await s.get(m.Agent, body.agent_id)
    if agent is None or agent.workspace_id != ws:
        raise not_found("agent", body.agent_id)
    row = Slo(
        id=new_id("slo"), workspace_id=ws, agent_id=agent.id, metric=body.metric,
        objective=body.objective, window_days=body.window_days,
        burn_alerts=list(body.burn_alerts), enabled=body.enabled,
    )  # fmt: skip
    s.add(row)
    await audit(s, ws, actor, "slo.create", "slo", row.id,
                {"agent_id": agent.id, "metric": body.metric})  # fmt: skip
    await s.commit()
    await s.refresh(row)
    return _out(row)


async def list_slos(s: AsyncSession, ws: str) -> list[SloOut]:
    rows = (
        await s.execute(select(Slo).where(Slo.workspace_id == ws).order_by(Slo.created_at))
    ).scalars()
    return [_out(r) for r in rows]


async def get_slo(s: AsyncSession, ws: str, slo_id: str) -> SloOut:
    return _out(await _owned(s, ws, slo_id))


async def update_slo(s: AsyncSession, ws: str, slo_id: str, body: SloPatch, actor: str) -> SloOut:
    row = await _owned(s, ws, slo_id)
    if body.objective is not None:
        _check_objective(row.metric, body.objective)
        row.objective = body.objective
    if body.window_days is not None:
        row.window_days = body.window_days
    if body.burn_alerts is not None:
        row.burn_alerts = list(body.burn_alerts)
    if body.enabled is not None:
        row.enabled = body.enabled
    await audit(
        s, ws, actor, "slo.update", "slo", slo_id, {"fields": sorted(body.model_fields_set)}
    )
    await s.commit()
    await s.refresh(row)
    return _out(row)


async def delete_slo(s: AsyncSession, ws: str, slo_id: str, actor: str) -> None:
    row = await _owned(s, ws, slo_id)
    await s.delete(row)
    await audit(s, ws, actor, "slo.delete", "slo", slo_id, {})
    await s.commit()


# --------------------------------------------------------------------------- evaluation


async def _episode_rows(
    s: AsyncSession, slo: Slo, since: datetime, attack: bool
) -> list[tuple[datetime, str | None, int | None, int]]:
    q = (
        select(m.Episode.finished_at, m.Episode.outcome, m.Episode.latency_ms,
               m.Episode.cost_usd_micros)
        .join(m.Run, m.Run.id == m.Episode.run_id)
        .join(m.AgentVersion, m.AgentVersion.id == m.Run.agent_version_id)
        .where(
            m.AgentVersion.agent_id == slo.agent_id,
            m.Run.workspace_id == slo.workspace_id,
            m.Run.purpose == "eval",
            m.Run.attack.is_(attack),
            m.Episode.status == "done",
            m.Episode.finished_at >= since,
        )
        .order_by(m.Episode.finished_at.desc())
        .limit(MAX_SAMPLES)
    )  # fmt: skip
    return [(r[0], r[1], r[2], r[3]) for r in (await s.execute(q)).all() if r[0] is not None]


async def slo_samples(s: AsyncSession, slo: Slo, now: datetime) -> list[Sample]:
    since = now - timedelta(days=slo.window_days)
    if slo.metric == "prod_failure_rate":
        rows = (
            await s.execute(
                select(ProdConversation.ended_at, ProdConversation.signals)
                .where(
                    ProdConversation.workspace_id == slo.workspace_id,
                    ProdConversation.agent_id == slo.agent_id,
                    ProdConversation.ended_at >= since,
                )
                .limit(MAX_SAMPLES)
            )
        ).all()
        return [Sample(ts, sum(int(v) for v in sig.values()) == 0) for ts, sig in rows]
    eps = await _episode_rows(s, slo, since, attack=slo.metric == "attack_success_rate")
    if slo.metric in ("pass_rate", "attack_success_rate"):
        return [Sample(ts, out == "passed") for ts, out, _, _ in eps if out in ("passed", "failed")]
    if slo.metric == "latency_p95":
        return [Sample(ts, lat <= slo.objective) for ts, _, lat, _ in eps if lat is not None]
    return [Sample(ts, cost <= slo.objective) for ts, _, _, cost in eps]


def _required_good(slo: Slo) -> float:
    if slo.metric == "pass_rate":
        return slo.objective
    if slo.metric in ("attack_success_rate", "prod_failure_rate"):
        return 1.0 - slo.objective
    return P95


def status_of(slo: Slo, samples: list[Sample], now: datetime) -> SloStatus:
    return slo_status(samples, _required_good(slo), timedelta(days=slo.window_days), now)


def slo_status_out(slo: Slo, st: SloStatus) -> SloStatusOut:
    lower_is_better = slo.metric in ("attack_success_rate", "prod_failure_rate")
    value: float | None = st.compliance
    interval = st.interval
    if lower_is_better and value is not None and interval is not None:
        value, interval = 1.0 - value, (1.0 - interval[1], 1.0 - interval[0])
    elif slo.metric in ("latency_p95", "cost_per_episode"):
        value, interval = None, None  # a p95 bound is not a rate; state and burn carry the story
    return SloStatusOut(
        slo_id=slo.id, metric=slo.metric, objective=slo.objective, state=st.state, n=st.n,
        value=value, interval=interval, error_budget_remaining=st.error_budget_remaining,
        burn_rates=st.burn_rates, firing_burn_alerts=burn_alerts(st), breached=st.breached,
        warning=st.warning, window_days=slo.window_days,
    )  # fmt: skip


async def evaluate_slo(
    s: AsyncSession, ws: str, slo_id: str, now: datetime | None = None
) -> SloStatusOut:
    now = now or datetime.now(UTC)
    slo = await _owned(s, ws, slo_id)
    return slo_status_out(slo, status_of(slo, await slo_samples(s, slo, now), now))
