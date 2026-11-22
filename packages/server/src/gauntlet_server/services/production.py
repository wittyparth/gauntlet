"""Production conversations (P5-1): ingest, read model, evaluation, retention.

Everything is redacted before it is persisted; raw text never reaches the database, logs or
exceptions. Conversations hold no effects: they are evaluated into `purpose=import` runs
(CQ-P2, CQ-P6) that keep only verdicts and ids."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from typing import Any

from gauntlet_core.checks import detectors as detector_registry
from gauntlet_core.checks import evaluate_final
from gauntlet_core.ids import new_id
from gauntlet_core.ingest import Redactor, Span, group_spans, trace_to_events
from gauntlet_core.schema import Check, Event, Json, StateDiff, Trajectory
from gauntlet_core.validate import walk_check
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select, text, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import models as m
from ..db.prod_models import IngestStat, ProdConversation, ProdEvent, ProdSpanSeen
from ..deps import AppState
from ..errors import ApiError, not_found
from ..pagination import Page, paginate
from ..stores.jobs import PgJobQueue
from .audit import audit
from .jobs import JobContext, handler
from .policies import dump_doc
from .runs import agent_version_of, platform_version

__all__ = [
    "ConversationDetail",
    "ConversationOut",
    "EvalStarted",
    "EvaluateIn",
    "IngestResult",
    "ProductionStats",
    "enqueue_evaluate",
    "get_conversation",
    "ingest_spans",
    "list_conversations",
    "production_stats",
    "record_rejected",
    "sweep_retention",
]

SIGNALS = ("turns", "tool_calls", "tool_errors", "unmapped_spans")
_SIGNAL_NAME = re.compile(r"^[a-z_]{1,40}$")


class IngestResult(BaseModel):
    accepted_spans: int = 0
    duplicate_spans: int = 0
    sampled_out_spans: int = 0
    conversations: int = 0


class ConversationOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    agent_id: str | None
    external_session_id: str
    started_at: datetime
    ended_at: datetime
    event_count: int
    signals: dict[str, Any]
    redaction: dict[str, Any]
    run_id: str | None
    created_at: datetime


class ConversationDetail(ConversationOut):
    events: list[Event]


class ConversationsPage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ConversationOut]
    next_cursor: str | None


class DayStats(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day: date
    spans: int
    bytes: int
    rejected: int


class ProductionStats(BaseModel):
    model_config = ConfigDict(extra="forbid")
    window_days: int
    conversations: int
    spans: int
    bytes: int
    rejected: int
    redactions: dict[str, int]
    by_day: list[DayStats]


class NamedCheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    check: Check


class EvaluateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_version_id: str | None = None
    detectors: list[str] = Field(default_factory=lambda: ["pii", "secret"])
    checks: list[NamedCheckIn] = []


class EvalStarted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str


# -- ingest -------------------------------------------------------------------------------


def _kept(session_id: str, rate: float) -> bool:
    """Deterministic whole-session sampling."""
    if rate >= 1.0:
        return True
    h = int.from_bytes(hashlib.sha256(session_id.encode()).digest()[:4], "big") / 2**32
    return h < rate


def _signals(events: list[Event]) -> dict[str, int]:
    c = Counter(
        turns=sum(1 for e in events if e.kind == "user_message"),
        tool_calls=sum(1 for e in events if e.kind == "tool_call"),
        tool_errors=sum(
            1 for e in events if e.kind == "tool_result" and not e.payload.get("ok", True)
        ),
        unmapped_spans=sum(1 for e in events if e.kind == "sim_note"),
    )
    return {k: c[k] for k in SIGNALS}


async def _new_spans(s: AsyncSession, ws: str, spans: list[Span]) -> tuple[list[Span], int]:
    new: list[Span] = []
    for i in range(0, len(spans), 1000):
        chunk = spans[i : i + 1000]
        stmt = (
            insert(ProdSpanSeen)
            .values(
                [{"workspace_id": ws, "trace_id": x.trace_id, "span_id": x.span_id} for x in chunk]
            )
            .on_conflict_do_nothing()
            .returning(ProdSpanSeen.trace_id, ProdSpanSeen.span_id)
        )
        fresh = {(t, sp) for t, sp in (await s.execute(stmt)).all()}
        new += [x for x in chunk if (x.trace_id, x.span_id) in fresh]
    return new, len(spans) - len(new)


async def _trace_conversations(s: AsyncSession, ws: str, traces: set[str]) -> dict[str, str]:
    if not traces:
        return {}
    rows = (
        await s.execute(
            select(ProdSpanSeen.trace_id, ProdSpanSeen.conversation_id)
            .where(
                ProdSpanSeen.workspace_id == ws,
                ProdSpanSeen.trace_id.in_(traces),
                ProdSpanSeen.conversation_id.is_not(None),
            )
            .distinct()
        )
    ).all()
    return {t: c for t, c in rows if c}


async def _upsert_conversation(
    s: AsyncSession,
    ws: str,
    agent_id: str | None,
    external: str | None,
    conv_id: str | None,
    events: list[Event],
    counts: Counter[str],
) -> str:
    cond = (
        ProdConversation.id == conv_id
        if conv_id
        else ProdConversation.external_session_id == external
    )
    row = (
        await s.execute(
            select(ProdConversation)
            .where(ProdConversation.workspace_id == ws, cond)
            .with_for_update()
        )
    ).scalar_one_or_none()
    old: list[Event] = []
    if row is not None:
        old = [
            Event.model_validate(r.doc)
            for r in (
                await s.execute(
                    select(ProdEvent)
                    .where(ProdEvent.conversation_id == row.id)
                    .order_by(ProdEvent.seq)
                )
            ).scalars()
        ]
    merged = sorted([*old, *events], key=lambda e: e.sim_time)  # stable: old events first
    merged = [e.model_copy(update={"seq": i + 1}) for i, e in enumerate(merged)]
    if row is None:
        row = ProdConversation(
            id=new_id("pc"), workspace_id=ws, agent_id=agent_id, external_session_id=external or '',
            started_at=merged[0].sim_time, ended_at=merged[-1].sim_time,
            event_count=len(merged), signals=_signals(merged), redaction=dict(counts),
        )  # fmt: skip
        s.add(row)
        await s.flush()
    else:
        await s.execute(delete(ProdEvent).where(ProdEvent.conversation_id == row.id))
        row.started_at, row.ended_at = merged[0].sim_time, merged[-1].sim_time
        row.event_count, row.signals = len(merged), _signals(merged)
        total: Counter[str] = Counter({k: int(v) for k, v in row.redaction.items()})
        total.update(counts)
        row.redaction = dict(total)
        row.agent_id = row.agent_id or agent_id
    s.add_all(
        ProdEvent(conversation_id=row.id, seq=e.seq, kind=e.kind, doc=dump_doc(e)) for e in merged
    )
    return row.id


async def ingest_spans(
    s: AsyncSession,
    state: AppState,
    ws: str,
    spans: list[Span],
    *,
    nbytes: int,
    agent_id: str | None = None,
    untrusted_tools: list[str] | None = None,
) -> IngestResult:
    cfg = state.settings
    out = IngestResult()
    kept_groups: dict[str, list[Span]] = {}
    for sid, group in group_spans(spans).items():
        if _kept(sid, cfg.ingest_sample_rate):
            kept_groups[sid] = group
        else:
            out.sampled_out_spans += len(group)
    kept = [sp for g in kept_groups.values() for sp in g]
    fresh, out.duplicate_spans = await _new_spans(s, ws, kept)
    fresh_ids = {(x.trace_id, x.span_id) for x in fresh}
    # A late batch may lack the span that names the session: the trace's earlier spans know it.
    known = await _trace_conversations(s, ws, {x.trace_id for x in fresh})
    groups: dict[str, list[Span]] = {}
    for sid, group in kept_groups.items():
        for x in group:
            if (x.trace_id, x.span_id) in fresh_ids:
                key = f"conv:{known[x.trace_id]}" if x.trace_id in known else f"ext:{sid}"
                groups.setdefault(key, []).append(x)
    total: Counter[str] = Counter()
    redactor = Redactor(
        cfg.redaction_key(), ws
    )  # one key per workspace: tokens agree across batches
    for key, new in groups.items():
        conv = trace_to_events(new, untrusted_tools=untrusted_tools or [])
        if not conv.events:
            continue  # only structural spans: nothing to store
        before = Counter(redactor.counts)
        events = [
            e.model_copy(update={"payload": redactor.redact_json(e.payload)}) for e in conv.events
        ]
        if key.startswith("conv:"):
            target: str | None = key[5:]
            external = None
        else:
            target, external = None, redactor.redact_text(conv.session_id)
        delta = Counter(redactor.counts)
        delta.subtract(before)
        counts: Counter[str] = Counter({k: v for k, v in delta.items() if v > 0})
        conv_id = await _upsert_conversation(s, ws, agent_id, external, target, events, counts)
        await s.execute(
            update(ProdSpanSeen)
            .where(
                ProdSpanSeen.workspace_id == ws,
                tuple_(ProdSpanSeen.trace_id, ProdSpanSeen.span_id).in_(
                    [(x.trace_id, x.span_id) for x in new]
                ),
            )
            .values(conversation_id=conv_id)
        )
        total.update(counts)
        out.conversations += 1
    out.accepted_spans = len(fresh)
    await _bump_stats(s, ws, spans=len(fresh), nbytes=nbytes, rejected=0, redactions=total)
    return out


async def _bump_stats(
    s: AsyncSession, ws: str, *, spans: int, nbytes: int, rejected: int, redactions: Counter[str]
) -> None:
    day = datetime.now(UTC).date()
    row = (
        await s.execute(
            select(IngestStat)
            .where(IngestStat.workspace_id == ws, IngestStat.day == day)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        s.add(
            IngestStat(
                workspace_id=ws, day=day, spans=spans, bytes=nbytes, rejected=rejected,
                redactions=dict(redactions),
            )
        )  # fmt: skip
        return
    merged = Counter({k: int(v) for k, v in row.redactions.items()})
    merged.update(redactions)
    row.spans, row.bytes, row.rejected = (
        row.spans + spans,
        row.bytes + nbytes,
        row.rejected + rejected,
    )
    row.redactions = dict(merged)


async def record_rejected(state: AppState, ws: str, n: int) -> None:
    async with state.sm() as s, s.begin():
        await s.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"ingest:{ws}"})
        await _bump_stats(s, ws, spans=0, nbytes=0, rejected=n, redactions=Counter())


# -- reads --------------------------------------------------------------------------------


def _out(row: ProdConversation) -> dict[str, Any]:
    return ConversationOut.model_validate(row, from_attributes=True).model_dump()


async def list_conversations(
    s: AsyncSession,
    ws: str,
    *,
    agent_id: str | None,
    from_ts: datetime | None,
    to_ts: datetime | None,
    signal: str | None,
    q: str | None,
    limit: int,
    cursor: str | None,
) -> dict[str, Any]:
    query = select(ProdConversation).where(ProdConversation.workspace_id == ws)
    if agent_id:
        query = query.where(ProdConversation.agent_id == agent_id)
    if from_ts:
        query = query.where(ProdConversation.started_at >= from_ts)
    if to_ts:
        query = query.where(ProdConversation.started_at <= to_ts)
    if signal:
        if not _SIGNAL_NAME.match(signal):
            raise ApiError(422, "validation_error", "unknown signal")
        query = query.where(
            text("coalesce((prod_conversations.signals ->> :sig)::int, 0) > 0").bindparams(
                sig=signal
            )
        )
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.where(
            text(
                "EXISTS (SELECT 1 FROM prod_events e "
                "WHERE e.conversation_id = prod_conversations.id "
                "AND e.doc::text ILIKE :q ESCAPE '\\')"
            ).bindparams(q=like)
        )
    return await paginate(s, query, ProdConversation, Page(limit, cursor), _out)


async def get_conversation(s: AsyncSession, ws: str, conv_id: str) -> dict[str, Any]:
    row = await s.get(ProdConversation, conv_id)
    if row is None or row.workspace_id != ws:
        raise not_found("conversation", conv_id)
    events = (
        await s.execute(
            select(ProdEvent).where(ProdEvent.conversation_id == conv_id).order_by(ProdEvent.seq)
        )
    ).scalars()
    return {**_out(row), "events": [Event.model_validate(e.doc) for e in events]}


async def production_stats(s: AsyncSession, ws: str, window_days: int) -> ProductionStats:
    since = datetime.now(UTC).date() - timedelta(days=window_days - 1)
    rows = (
        (
            await s.execute(
                select(IngestStat)
                .where(IngestStat.workspace_id == ws, IngestStat.day >= since)
                .order_by(IngestStat.day)
            )
        )
        .scalars()
        .all()
    )
    red: Counter[str] = Counter()
    for r in rows:
        red.update({k: int(v) for k, v in r.redactions.items()})
    convs = (
        await s.execute(
            select(func.count())
            .select_from(ProdConversation)
            .where(ProdConversation.workspace_id == ws)
        )
    ).scalar_one()
    return ProductionStats(
        window_days=window_days,
        conversations=int(convs),
        spans=sum(r.spans for r in rows),
        bytes=sum(r.bytes for r in rows),
        rejected=sum(r.rejected for r in rows),
        redactions=dict(red),
        by_day=[
            DayStats(day=r.day, spans=r.spans, bytes=r.bytes, rejected=r.rejected) for r in rows
        ],
    )


# -- evaluation ---------------------------------------------------------------------------


async def _agent_version(s: AsyncSession, ws: str, conv: ProdConversation, vid: str | None):
    if vid:
        av = await s.get(m.AgentVersion, vid)
        if av is None or av.workspace_id != ws:
            raise not_found("agent version", vid)
        return av
    if conv.agent_id is None:
        raise ApiError(422, "no_agent", "the conversation has no agent: pass agent_version_id")
    av = (
        await s.execute(
            select(m.AgentVersion)
            .where(m.AgentVersion.workspace_id == ws, m.AgentVersion.agent_id == conv.agent_id)
            .order_by(m.AgentVersion.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if av is None:
        raise ApiError(422, "no_agent", "the agent has no versions")
    return av


async def enqueue_evaluate(
    state: AppState, s: AsyncSession, ws: str, conv_id: str, body: EvaluateIn, actor: str
) -> EvalStarted:
    conv = await s.get(ProdConversation, conv_id)
    if conv is None or conv.workspace_id != ws:
        raise not_found("conversation", conv_id)
    av = await _agent_version(s, ws, conv, body.agent_version_id)
    unknown = [d for d in body.detectors if d not in detector_registry.names()]
    if unknown:
        raise ApiError(422, "unknown_detector", f"unknown detectors: {', '.join(unknown)}")
    job_id = await PgJobQueue(state.sm).enqueue(
        ws,
        "evaluate_conversation",
        {
            "conversation_id": conv_id,
            "agent_version_id": av.id,
            "detectors": body.detectors,
            "checks": [
                {
                    "id": c.id,
                    "check": c.check.model_dump(mode="json", by_alias=True, exclude_defaults=True),
                }
                for c in body.checks
            ],
        },
        session=s,
    )  # fmt: skip
    await audit(
        s, ws, actor, "production.evaluate_requested", "conversation", conv_id, {"job_id": job_id}
    )
    await s.commit()
    return EvalStarted(job_id=job_id)


def _trajectory(conv_id: str, events: list[Event]) -> Trajectory:
    return Trajectory.model_construct(
        episode_id=conv_id, scenario=None, events=events, initial_world={}, final_world={},
        diff=StateDiff(), canaries=[], tool_risk={}, honeytools=[],
    )  # fmt: skip


def _verdict(
    criterion: str, evaluator: str, holds: bool, evidence: list[Json], na: bool
) -> dict[str, Any]:
    result = "na" if na else ("fail" if holds else "pass")
    return {"evaluator": evaluator, "criterion": criterion, "result": result, "evidence": evidence}


@handler("evaluate_conversation")
async def evaluate_job(ctx: JobContext) -> dict[str, Any]:
    from pydantic import TypeAdapter

    p, ws = ctx.payload, ctx.workspace_id
    adapter: TypeAdapter[Check] = TypeAdapter(Check)
    async with ctx.state.sm() as s, s.begin():
        conv = await s.get(ProdConversation, str(p["conversation_id"]))
        assert conv is not None
        events = [
            Event.model_validate(r.doc)
            for r in (
                await s.execute(
                    select(ProdEvent)
                    .where(ProdEvent.conversation_id == conv.id)
                    .order_by(ProdEvent.seq)
                )
            ).scalars()
        ]
        traj = _trajectory(conv.id, events)
        verdicts: list[dict[str, Any]] = []
        for name in p.get("detectors", []):
            res = detector_registry.get(name)(traj, {})
            verdicts.append(
                _verdict(
                    name,
                    "detector",
                    res.holds,
                    [e.model_dump(mode="json") for e in res.evidence],
                    False,
                )
            )
        for item in p.get("checks", []):
            check = adapter.validate_python(item["check"])
            world_bound = any(n.type in ("state", "state_diff") for n in walk_check(check))
            res = evaluate_final(check, traj)  # world checks cannot be decided: reported as na
            verdicts.append(
                _verdict(
                    item["id"],
                    "check",
                    res.holds,
                    [e.model_dump(mode="json") for e in res.evidence],
                    world_bound,
                )
            )
        av = await s.get(m.AgentVersion, str(p["agent_version_id"]))
        assert av is not None
        suite_id = "suite_production_" + hashlib.sha256(ws.encode()).hexdigest()[:8]
        if await s.get(m.Suite, suite_id) is None:
            s.add(
                m.Suite(id=suite_id, workspace_id=ws, name="Production evaluations", repetitions=1)
            )
            await s.flush()
        from gauntlet_core.schema import RunManifest

        run_id, ep_id, now = new_id("run"), new_id("ep"), datetime.now(UTC)
        manifest = RunManifest(
            run_id=run_id, suite_id=suite_id, agent_version=agent_version_of(av),
            scenario_versions={}, seed=0, repetitions=1, model_roles={},
            platform_version=platform_version(), budget_usd_micros=0, created_at=now,
        )  # fmt: skip
        s.add(
            m.Run(
                id=run_id, workspace_id=ws, suite_id=suite_id, agent_version_id=av.id,
                manifest=manifest.model_dump(mode="json"), status="done", repetitions=1, seed=0,
                world_versions={}, budget_usd_micros=0, purpose="import", finished_at=now,
            )
        )  # fmt: skip
        await s.flush()
        failed = any(v["result"] == "fail" for v in verdicts)
        s.add(
            m.Episode(
                id=ep_id, workspace_id=ws, run_id=run_id, scenario_id=f"prod:{conv.id}",
                scenario_version=1, rep=0, status="done",
                outcome="failed" if failed else "passed", termination="user_done", epoch=0,
                rng_seed=0, latency_ms=0, tokens_in=0, tokens_out=0, finished_at=now,
            )
        )  # fmt: skip
        await s.flush()
        for v in verdicts:
            s.add(
                m.Verdict(
                    id=new_id("vrd"), workspace_id=ws, episode_id=ep_id, evaluator=v["evaluator"],
                    criterion=v["criterion"], result=v["result"], doc=v,
                )
            )  # fmt: skip
        conv.run_id = run_id
        await audit(s, ws, "system", "production.evaluated", "conversation", conv.id,
                    {"run_id": run_id, "failed": failed})  # fmt: skip
    return {"run_id": run_id, "episode_id": ep_id, "verdicts": len(verdicts), "failed": failed}


# -- retention ----------------------------------------------------------------------------


async def sweep_retention(
    state: AppState, *, now: datetime | None = None, batch: int = 1000
) -> dict[str, int]:
    """Delete conversations older than the retention (events cascade) and their span markers,
    in batches. Import runs made from them keep only ids and verdicts (CQ-P6)."""
    cutoff = (now or datetime.now(UTC)) - timedelta(days=state.settings.prod_retention_days)
    deleted = markers = 0
    while True:
        async with state.sm() as s, s.begin():
            ids = list(
                (
                    await s.execute(
                        text(
                            "SELECT id FROM prod_conversations WHERE ended_at < :c "
                            "ORDER BY ended_at LIMIT :n FOR UPDATE SKIP LOCKED"
                        ),
                        {"c": cutoff, "n": batch},
                    )
                ).scalars()
            )
            if not ids:
                break
            await s.execute(delete(ProdConversation).where(ProdConversation.id.in_(ids)))
            deleted += len(ids)
    while True:
        async with state.sm() as s, s.begin():
            res = await s.execute(
                text(
                    "DELETE FROM prod_spans_seen WHERE ctid IN (SELECT ctid FROM prod_spans_seen "
                    "WHERE created_at < :c LIMIT :n)"
                ),
                {"c": cutoff, "n": batch},
            )
            n = int(res.rowcount or 0)  # type: ignore[attr-defined]
            markers += n
            if n < batch:
                break
    return {"conversations": deleted, "span_markers": markers}
