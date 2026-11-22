"""Failure mining and conversion of production conversations (P5-2).

A mining run scores the conversations of an agent in a window (deterministic signals first,
an optional sampled judge on a calibrated rubric second), clusters the failing ones and keeps
the top candidates. Conversion anonymises again, checks k-anonymity, asks the `generator` role
for the story and stores a *draft* scenario: a person approves it before it can run. Both jobs
are metered against the budget given at request time."""

from __future__ import annotations

import base64
import hashlib
import json
from collections import Counter
from datetime import datetime
from typing import Any, Literal

from gauntlet_core.eval.cluster import MemoryNameCache, name_cluster
from gauntlet_core.eval.cluster.group import group_failures
from gauntlet_core.eval.cluster.name import Exemplar
from gauntlet_core.ids import new_id
from gauntlet_core.llm.types import LLMResult
from gauntlet_core.mining import (
    ConversionFailed,
    DetectorSpec,
    anonymise,
    score_conversation,
    to_scenario,
)
from gauntlet_core.mining.prompts import render_transcript
from gauntlet_core.schema import Event, Rubric, WorldSpec
from gauntlet_core.sim import load_persona_library
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import models as m
from ..db.prod_models import MiningCandidate, MiningRun, ProdConversation, ProdEvent
from ..db.review_models import Calibration
from ..deps import AppState
from ..errors import ApiError, not_found
from ..stores.jobs import PgJobQueue
from .audit import audit
from .findings import upsert_scenario
from .jobs import JobContext, handler

__all__ = [
    "CandidateDetail",
    "CandidateOut",
    "CandidatesPage",
    "ConvertStarted",
    "MineIn",
    "MiningRunOut",
    "MiningStarted",
    "dismiss_candidate",
    "enqueue_convert",
    "enqueue_mine",
    "get_candidate",
    "get_mining_run",
    "list_candidates",
]

SCAN_CAP = 2000
K_ANONYMITY = 3
DEFAULT_DETECTORS = ["markdown_image_exfil", "profanity", "secret"]


class MineIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    agent_id: str
    from_ts: datetime | None = Field(default=None, alias="from")
    to_ts: datetime | None = Field(default=None, alias="to")
    limit: int = Field(default=50, ge=1, le=500)
    budget_usd_micros: int = Field(gt=0)  # mining refuses to start without a budget
    detectors: list[str] = Field(default_factory=lambda: list(DEFAULT_DETECTORS))
    rubric_id: str | None = None  # must be calibrated for gating
    judge_sample: float = Field(default=0.1, ge=0.0, le=1.0)


class MiningStarted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    mining_run_id: str


class MiningRunOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    agent_id: str
    window: dict[str, Any]
    status: str
    counts: dict[str, Any]
    budget_usd_micros: int
    spent_usd_micros: int
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class CandidateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    mining_run_id: str
    conversation_id: str
    score: float
    parts: dict[str, Any]
    reasons: list[str]
    detector_hits: list[str]
    cluster_id: str | None
    cluster_name: str | None
    status: Literal["new", "converted", "dismissed"]
    dismissed_reason: str | None
    scenario_id: str | None
    convert_error: str | None
    created_at: datetime


class CandidateDetail(CandidateOut):
    events: list[Event]


class CandidatesPage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[CandidateOut]
    next_cursor: str | None


class ConvertStarted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str


class _Meter:
    def __init__(self, gateway: Any, budget: int) -> None:
        self.gateway, self.budget, self.spent = gateway, budget, 0

    @property
    def exhausted(self) -> bool:
        return self.spent >= self.budget

    async def complete(self, *args: Any, **kw: Any) -> LLMResult:
        res: LLMResult = await self.gateway.complete(*args, **kw)
        self.spent += res.cost.usd_micros
        return res

    def __getattr__(self, name: str) -> Any:
        return getattr(self.gateway, name)


class JudgeVerdict(BaseModel):
    result: Literal["pass", "fail", "na"]


# -- enqueue ------------------------------------------------------------------------------


async def _calibrated(s: AsyncSession, ws: str, rubric_id: str) -> Rubric:
    row = (
        await s.execute(
            select(m.Rubric)
            .where(m.Rubric.workspace_id == ws, m.Rubric.id == rubric_id)
            .order_by(m.Rubric.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise not_found("rubric", rubric_id)
    ok = (
        await s.execute(
            select(Calibration.id)
            .where(
                Calibration.workspace_id == ws,
                Calibration.rubric_id == rubric_id,
                Calibration.status == "done",
                Calibration.gating_allowed.is_(True),
                Calibration.stale.is_(False),
            )
            .limit(1)
        )
    ).first()
    if ok is None:
        raise ApiError(
            422, "rubric_not_calibrated", "only a calibrated rubric may judge production traffic"
        )
    return Rubric.model_validate(row.doc)


async def enqueue_mine(
    state: AppState, s: AsyncSession, ws: str, body: MineIn, actor: str
) -> MiningStarted:
    from gauntlet_core.checks import detectors as registry

    agent = await s.get(m.Agent, body.agent_id)
    if agent is None or agent.workspace_id != ws:
        raise not_found("agent", body.agent_id)
    unknown = [d for d in body.detectors if d not in registry.names()]
    if unknown:
        raise ApiError(422, "unknown_detector", f"unknown detectors: {', '.join(unknown)}")
    if body.rubric_id:
        await _calibrated(s, ws, body.rubric_id)
    run = MiningRun(
        id=new_id("mrun"),
        workspace_id=ws,
        agent_id=agent.id,
        window={
            "from": body.from_ts.isoformat() if body.from_ts else None,
            "to": body.to_ts.isoformat() if body.to_ts else None,
        },
        status="queued",
        budget_usd_micros=body.budget_usd_micros,
    )
    s.add(run)
    await s.flush()
    job_id = await PgJobQueue(state.sm).enqueue(
        ws,
        "mine_failures",
        {
            "mining_run_id": run.id,
            "limit": body.limit,
            "detectors": body.detectors,
            "rubric_id": body.rubric_id,
            "judge_sample": body.judge_sample,
        },
        session=s,
    )
    await audit(s, ws, actor, "production.mine_requested", "mining_run", run.id, {"job_id": job_id})
    await s.commit()
    return MiningStarted(job_id=job_id, mining_run_id=run.id)


# -- the mining job -----------------------------------------------------------------------


def _sampled(conv_id: str, rate: float) -> bool:
    h = int.from_bytes(hashlib.sha256(conv_id.encode()).digest()[:4], "big") / 2**32
    return h < rate


def _judge_for(rubric: Rubric, meter: _Meter, counts: Counter[str], rate: float):
    async def judge(events: list[Event], conv_id: str) -> float | None:
        if not _sampled(conv_id, rate) or meter.exhausted:
            if meter.exhausted:
                counts["budget_exhausted"] = 1
            return None
        messages = [
            {
                "role": "system",
                "content": (
                    f"Grade one conversation. Question: {rubric.question}\n"
                    f"pass: {rubric.pass_definition}\nfail: {rubric.fail_definition}\n"
                    'Reply with JSON {"result": "pass" | "fail" | "na"}.'
                ),
            },
            {"role": "user", "content": render_transcript(events)},
        ]
        try:
            res = await meter.complete(
                "judge_small", messages, response_model=JudgeVerdict, temperature=0.0
            )
        except Exception:
            counts["judge_errors"] += 1
            return None
        counts["judged"] += 1
        return 1.0 if isinstance(res.parsed, JudgeVerdict) and res.parsed.result == "fail" else 0.0

    return judge


async def _events(s: AsyncSession, conv_id: str) -> list[Event]:
    rows = (
        await s.execute(
            select(ProdEvent).where(ProdEvent.conversation_id == conv_id).order_by(ProdEvent.seq)
        )
    ).scalars()
    return [Event.model_validate(r.doc) for r in rows]


@handler("mine_failures")
async def mine_job(ctx: JobContext) -> dict[str, Any]:
    from gauntlet_core.eval.cluster import embed_texts

    p, ws = ctx.payload, ctx.workspace_id
    meter = _Meter(ctx.state.gateway, 0)
    counts: Counter[str] = Counter()
    async with ctx.state.sm() as s:
        run = await s.get(MiningRun, str(p["mining_run_id"]))
        assert run is not None
        meter.budget = run.budget_usd_micros
        rubric = await _calibrated(s, ws, p["rubric_id"]) if p.get("rubric_id") else None
        q = (
            select(ProdConversation.id)
            .where(ProdConversation.workspace_id == ws, ProdConversation.agent_id == run.agent_id)
            .order_by(ProdConversation.started_at.desc())
            .limit(SCAN_CAP)
        )
        if run.window.get("from"):
            q = q.where(ProdConversation.started_at >= datetime.fromisoformat(run.window["from"]))
        if run.window.get("to"):
            q = q.where(ProdConversation.started_at <= datetime.fromisoformat(run.window["to"]))
        ids = list((await s.execute(q)).scalars())
        await s.execute(
            text("UPDATE mining_runs SET status = 'running' WHERE id = :i"), {"i": run.id}
        )
        await s.commit()
        detectors = [DetectorSpec(name=n) for n in p.get("detectors", [])]
        scored: list[tuple[str, Any, list[Event]]] = []
        for cid in ids:
            events = await _events(s, cid)
            judge = (
                _judge_for(rubric, meter, counts, float(p.get("judge_sample", 0.1)))
                if rubric
                else None
            )

            async def bound(evs, _cid=cid, _judge=judge):
                return await _judge(list(evs), _cid) if _judge else None

            sc = await score_conversation(events, detectors, judge=bound if judge else None)
            counts["scanned"] += 1
            if sc.total > 0:
                scored.append((cid, sc, events))
    scored.sort(key=lambda t: (-t[1].total, t[0]))
    top = scored[: int(p.get("limit", 50))]
    labels: list[int] = []
    if top:
        vectors = await embed_texts([render_transcript(e) for _, _, e in top], None)
        labels = group_failures(vectors, [sorted(sc.parts) for _, sc, _ in top])
    names: dict[int, str] = {}
    cache = MemoryNameCache()
    for label in sorted({lb for lb in labels if lb >= 0}):
        members = [i for i, lb in enumerate(labels) if lb == label]
        if len(members) < 2:
            continue
        top_part = Counter(part for i in members for part in top[i][1].parts).most_common(1)[0][0]
        fallback = f"Cluster {label}: {top_part}"
        if meter.exhausted:
            names[label] = fallback
            counts["budget_exhausted"] = 1
            continue
        named = await name_cluster(
            [Exemplar(top[i][0], render_transcript(top[i][2])[:600]) for i in members[:4]],
            meter,  # type: ignore[arg-type]
            fallback=fallback,
            member_ids=[top[i][0] for i in members],
            cache=cache,
        )
        names[label] = named.name
    async with ctx.state.sm() as s, s.begin():
        for i, (cid, sc, _) in enumerate(top):
            lb = labels[i] if labels else -1
            s.add(
                MiningCandidate(
                    id=new_id("cand"),
                    workspace_id=ws,
                    mining_run_id=str(p["mining_run_id"]),
                    conversation_id=cid,
                    score=sc.total,
                    parts=sc.parts,
                    reasons=sc.reasons,
                    detector_hits=sc.detector_hits,
                    cluster_id=f"cl{lb}" if lb >= 0 and lb in names else None,
                    cluster_name=names.get(lb),
                )
            )
        counts["candidates"] = len(top)
        await s.execute(
            text(
                "UPDATE mining_runs SET status = 'done', counts = CAST(:c AS jsonb), "
                "spent_usd_micros = :sp, finished_at = now() WHERE id = :i"
            ),
            {"c": json.dumps(dict(counts)), "sp": meter.spent, "i": str(p["mining_run_id"])},
        )
        await audit(
            s,
            ws,
            "system",
            "production.mined",
            "mining_run",
            str(p["mining_run_id"]),
            {"candidates": len(top), "spent_usd_micros": meter.spent},
        )
    return {"mining_run_id": p["mining_run_id"], **counts, "spent_usd_micros": meter.spent}


# -- reads --------------------------------------------------------------------------------


def _out(c: MiningCandidate) -> CandidateOut:
    return CandidateOut(
        id=c.id,
        mining_run_id=c.mining_run_id,
        conversation_id=c.conversation_id,
        score=c.score,
        parts=c.parts,
        reasons=list(c.reasons),
        detector_hits=list(c.detector_hits),
        cluster_id=c.cluster_id,
        cluster_name=c.cluster_name,
        status=c.status,  # type: ignore[arg-type]
        dismissed_reason=c.dismissed_reason,
        scenario_id=c.scenario_id,
        convert_error=c.convert_error,
        created_at=c.created_at,
    )


async def get_mining_run(s: AsyncSession, ws: str, run_id: str) -> MiningRunOut:
    row = await s.get(MiningRun, run_id)
    if row is None or row.workspace_id != ws:
        raise not_found("mining run", run_id)
    return MiningRunOut.model_validate(row, from_attributes=True)


def _cursor(score: float, id_: str) -> str:
    return base64.urlsafe_b64encode(json.dumps([score, id_]).encode()).decode()


async def list_candidates(
    s: AsyncSession,
    ws: str,
    *,
    mining_run_id: str | None,
    status: str | None,
    cluster: str | None,
    limit: int,
    cursor: str | None,
) -> CandidatesPage:
    limit = max(1, min(limit, 200))
    q = select(MiningCandidate).where(MiningCandidate.workspace_id == ws)
    if mining_run_id:
        q = q.where(MiningCandidate.mining_run_id == mining_run_id)
    if status:
        q = q.where(MiningCandidate.status == status)
    if cluster:
        q = q.where(MiningCandidate.cluster_id == cluster)
    if cursor:
        try:
            score, cid = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        except (ValueError, TypeError) as e:
            raise ApiError(422, "validation_error", "invalid cursor") from e
        q = q.where(
            (MiningCandidate.score < score)
            | ((MiningCandidate.score == score) & (MiningCandidate.id > cid))
        )
    q = q.order_by(MiningCandidate.score.desc(), MiningCandidate.id).limit(limit + 1)
    rows = list((await s.execute(q)).scalars())
    more = len(rows) > limit
    rows = rows[:limit]
    return CandidatesPage(
        items=[_out(r) for r in rows],
        next_cursor=_cursor(rows[-1].score, rows[-1].id) if more and rows else None,
    )


async def _owned(s: AsyncSession, ws: str, cand_id: str) -> MiningCandidate:
    row = await s.get(MiningCandidate, cand_id)
    if row is None or row.workspace_id != ws:
        raise not_found("candidate", cand_id)
    return row


async def get_candidate(s: AsyncSession, ws: str, cand_id: str) -> CandidateDetail:
    row = await _owned(s, ws, cand_id)
    return CandidateDetail(**_out(row).model_dump(), events=await _events(s, row.conversation_id))


async def dismiss_candidate(s: AsyncSession, ws: str, cand_id: str, actor: str) -> CandidateOut:
    row = await _owned(s, ws, cand_id)
    if row.status == "converted":
        raise ApiError(409, "conflict", "a converted candidate cannot be dismissed")
    row.status, row.dismissed_reason = "dismissed", "dismissed by a reviewer"
    await audit(s, ws, actor, "production.candidate_dismissed", "candidate", row.id, {})
    await s.commit()
    return _out(row)


# -- conversion ---------------------------------------------------------------------------


async def enqueue_convert(
    state: AppState, s: AsyncSession, ws: str, cand_id: str, actor: str
) -> ConvertStarted:
    row = await _owned(s, ws, cand_id)
    if row.status != "new":
        raise ApiError(409, "conflict", f"the candidate is {row.status}")
    job_id = await PgJobQueue(state.sm).enqueue(
        ws, "convert_candidate", {"candidate_id": row.id}, session=s
    )
    await audit(
        s, ws, actor, "production.convert_requested", "candidate", row.id, {"job_id": job_id}
    )
    await s.commit()
    return ConvertStarted(job_id=job_id)


async def _other_conversations_with(s: AsyncSession, ws: str, conv_id: str, value: str) -> int:
    like = "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    n = (
        await s.execute(
            text(
                "SELECT count(DISTINCT e.conversation_id) FROM prod_events e "
                "JOIN prod_conversations c ON c.id = e.conversation_id "
                "WHERE c.workspace_id = :ws AND e.conversation_id <> :cid "
                "AND e.doc::text ILIKE :v ESCAPE '\\'"
            ),
            {"ws": ws, "cid": conv_id, "v": like},
        )
    ).scalar_one()
    return int(n)


@handler("convert_candidate")
async def convert_job(ctx: JobContext) -> dict[str, Any]:
    ws = ctx.workspace_id
    async with ctx.state.sm() as s:
        cand = await s.get(MiningCandidate, str(ctx.payload["candidate_id"]))
        assert cand is not None
        if cand.status != "new":
            return {"status": cand.status, "scenario_id": cand.scenario_id}  # at-least-once
        run = await s.get(MiningRun, cand.mining_run_id)
        assert run is not None
        av = (
            await s.execute(
                select(m.AgentVersion)
                .where(m.AgentVersion.workspace_id == ws, m.AgentVersion.agent_id == run.agent_id)
                .order_by(m.AgentVersion.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if av is None or not av.world_id:
            raise ApiError(422, "no_world", "the agent has no world to convert into")
        wrow = (
            await s.execute(
                select(m.World)
                .where(m.World.workspace_id == ws, m.World.id == av.world_id)
                .order_by(m.World.version.desc())
                .limit(1)
            )
        ).scalar_one()
        world = WorldSpec.model_validate(wrow.doc)
        events = await _events(s, cand.conversation_id)
        personas = set(load_persona_library())
        personas |= set(
            (await s.execute(select(m.Persona.id).where(m.Persona.workspace_id == ws))).scalars()
        )
        seed = int.from_bytes(hashlib.sha256(cand.id.encode()).digest()[:4], "big")
        anon = anonymise(events, seed=seed)
        rare = [
            r
            for r in anon.residual
            if await _other_conversations_with(s, ws, cand.conversation_id, r.value) < K_ANONYMITY
        ]
    if rare:  # a quasi-identifier we could not replace and few others share: never convert
        async with ctx.state.sm() as s, s.begin():
            c2 = await s.get(MiningCandidate, cand.id)
            assert c2 is not None
            c2.status, c2.dismissed_reason = "dismissed", "k_anonymity"
            await audit(
                s,
                ws,
                "system",
                "production.candidate_excluded",
                "candidate",
                cand.id,
                {"reason": "k_anonymity", "kinds": sorted({r.kind for r in rare})},
            )
        return {"status": "dismissed", "reason": "k_anonymity"}
    meter = _Meter(ctx.state.gateway, 0)
    try:
        draft = await to_scenario(
            events,
            conv_ref=cand.conversation_id,
            world=world,
            gateway=meter,  # type: ignore[arg-type]
            seed=seed,
            detector_hits=list(cand.detector_hits),
            persona_ids=sorted(personas),
            anonymised=anon,
        )
    except ConversionFailed as e:
        async with ctx.state.sm() as s, s.begin():
            await audit(
                s,
                ws,
                "system",
                "production.conversion_failed",
                "candidate",
                cand.id,
                {"reasons": e.reasons},
            )
            c3 = await s.get(MiningCandidate, cand.id)
            assert c3 is not None
            c3.convert_error = ", ".join(e.reasons)
        # deterministic: retrying the job would fail the same way, so the job itself is done
        return {"status": "failed", "reasons": e.reasons}
    async with ctx.state.sm() as s, s.begin():
        c2 = await s.get(MiningCandidate, cand.id)
        assert c2 is not None
        await upsert_scenario(s, ws, draft.scenario, "mined", status="draft")
        c2.status, c2.scenario_id = "converted", draft.scenario.id
        await audit(
            s,
            ws,
            "system",
            "production.converted",
            "candidate",
            cand.id,
            {"scenario_id": draft.scenario.id, "needs_review": draft.needs_review},
        )
    return {
        "status": "converted",
        "scenario_id": draft.scenario.id,
        "needs_review": draft.needs_review,
        "notes": draft.notes,
        "cost_usd_micros": meter.spent,
    }
