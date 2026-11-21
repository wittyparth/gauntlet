"""Failure clustering job and read model (P3-6): failed episodes of a run are embedded (offline
`HashEmbedder` unless the workspace opted into a catalog model), grouped with HDBSCAN, named and
given a root cause. Idempotent: a re-run replaces the run's clusters and embeddings."""

from __future__ import annotations

import hashlib
import logging
from collections import Counter
from typing import Any, Literal

from gauntlet_core.eval.cluster import (
    EMBED_DIM,
    Attribution,
    Exemplar,
    MemoryNameCache,
    attribute_episode,
    cluster_root_cause,
    embed_texts,
    failed_check_ids,
    failure_text,
    group_failures,
    name_cluster,
)
from gauntlet_core.ids import new_id
from gauntlet_core.llm.types import LLMResult
from gauntlet_core.schema import SEVERITY_ORDER, Scenario, Trajectory, Verdict
from gauntlet_core.world import build_trajectory, build_world
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.cluster_models import FailureCluster, FailureEmbedding
from ..db.models import Episode, Run
from ..deps import AppState
from ..errors import ApiError, not_found
from ..jobs import load_episode_inputs
from ..models_gateway import gateway_for_roles
from ..stores.jobs import PgJobQueue
from .audit import audit
from .jobs import JobContext, handler
from .reports import _events, episode_verdicts

__all__ = [
    "ClusterOut",
    "ClusterStarted",
    "ClustersOut",
    "clusters_for_run",
    "enqueue_cluster",
    "run_clustering",
]

log = logging.getLogger("gauntlet.clusters")
NAMES = MemoryNameCache()  # per process: naming the same members again costs nothing
EXEMPLARS = 6


class ClusterOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    label: int
    name: str
    description: str
    suspected_cause: str
    root_cause: str
    root_cause_share: float
    size: int
    episode_ids: list[str]
    scenario_ids: list[str]
    exemplar_episode_id: str | None
    max_severity: str | None


class ClustersOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["none", "queued", "running", "done", "failed"]
    clusters: list[ClusterOut]
    unclustered: list[str]


class ClusterStarted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str


async def _owned_run(s: AsyncSession, ws: str, run_id: str) -> Run:
    run = await s.get(Run, run_id)
    if run is None or run.workspace_id != ws:
        raise not_found("run", run_id)
    return run


async def enqueue_cluster(
    state: AppState, s: AsyncSession, ws: str, run_id: str, actor: str = "system"
) -> str:
    run = await _owned_run(s, ws, run_id)
    if run.status != "done":
        raise ApiError(409, "run_not_completed", "only a completed run can be clustered")
    job_id = await PgJobQueue(state.sm).enqueue(ws, "cluster", {"run_id": run_id}, session=s)
    await audit(s, ws, actor, "run.cluster_requested", "run", run_id, {"job_id": job_id})
    await s.commit()
    return job_id


async def clusters_for_run(s: AsyncSession, ws: str, run_id: str) -> ClustersOut:
    await _owned_run(s, ws, run_id)
    rows = (
        (
            await s.execute(
                select(FailureCluster)
                .where(FailureCluster.run_id == run_id)
                .order_by(FailureCluster.label)
            )
        )
        .scalars()
        .all()
    )
    job = (
        await s.execute(
            text(
                "SELECT status FROM jobs WHERE workspace_id = :ws AND kind = 'cluster' "
                "AND payload->>'run_id' = :r ORDER BY created_at DESC, id DESC LIMIT 1"
            ),
            {"ws": ws, "r": run_id},
        )
    ).scalar()
    status: Any = job or ("done" if rows else "none")
    members = {e for c in rows for e in c.member_episode_ids}
    embedded = list(
        (
            await s.execute(
                select(FailureEmbedding.episode_id)
                .where(FailureEmbedding.run_id == run_id)
                .order_by(FailureEmbedding.episode_id)
            )
        ).scalars()
    )
    return ClustersOut(
        status=status,
        clusters=[
            ClusterOut(
                id=c.id,
                label=c.label,
                name=c.name,
                description=c.description,
                suspected_cause=c.suspected_cause,
                root_cause=c.root_cause,
                root_cause_share=c.root_cause_share,
                size=len(c.member_episode_ids),
                episode_ids=list(c.member_episode_ids),
                scenario_ids=list(c.scenario_ids),
                exemplar_episode_id=c.exemplar_episode_id,
                max_severity=c.max_severity,
            )
            for c in rows
        ],
        unclustered=[e for e in embedded if e not in members],
    )


class _Metered:
    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.usd = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    async def complete(self, *args: Any, **kw: Any) -> LLMResult:
        res: LLMResult = await self.inner.complete(*args, **kw)
        self.usd += res.cost.usd_micros
        return res


class _Failure:
    def __init__(
        self,
        episode_id: str,
        scenario: Scenario,
        traj: Trajectory,
        verdicts: list[Verdict],
        checks: list[dict[str, Any]],
    ) -> None:
        self.episode_id, self.scenario, self.traj = episode_id, scenario, traj
        self.verdicts, self.checks = verdicts, checks
        self.text = failure_text(traj, verdicts, checks, "failed")
        self.failed = failed_check_ids(checks)
        self.attribution: Attribution | None = None

    def severity(self) -> str:
        """Highest severity among the failed checks and failing hard-fail verdicts; a failure
        with neither (a forced outcome) counts as medium."""
        sev = {n.id: n.severity for n in self.scenario.forbidden}
        sev["success"] = "high"
        levels = [sev.get(c, "medium") for c in self.failed]
        levels += [v.severity for v in self.verdicts if v.result == "fail" and v.hard_fail]
        return max(levels or ["medium"], key=lambda v: SEVERITY_ORDER[v])  # type: ignore[index]


async def _load_failures(s: AsyncSession, run_id: str) -> list[_Failure]:
    eps = (
        (
            await s.execute(
                select(Episode)
                .where(
                    Episode.run_id == run_id,
                    Episode.status == "done",
                    Episode.outcome == "failed",
                )
                .order_by(Episode.id)
            )
        )
        .scalars()
        .all()
    )
    out: list[_Failure] = []
    for ep in eps:
        inputs = await load_episode_inputs(s, ep.id)
        events = await _events(s, ep.id)
        built = build_world(inputs.world, inputs.scenario.world_overrides, int(ep.rng_seed))
        traj = build_trajectory(ep.id, inputs.scenario, events, built)
        checks = [dict(e.payload) for e in events if e.kind == "check_result"]
        out.append(
            _Failure(ep.id, inputs.scenario, traj, await episode_verdicts(s, ep.id, events), checks)
        )
    return out


def _centroid_order(vectors: list[list[float]], idx: list[int]) -> list[int]:
    """Members sorted by distance to their centroid, nearest first."""
    dim = len(vectors[0])
    centre = [sum(vectors[i][d] for i in idx) / len(idx) for d in range(dim)]

    def dist(i: int) -> float:
        return sum((vectors[i][d] - centre[d]) ** 2 for d in range(dim))

    return sorted(idx, key=lambda i: (dist(i), i))


async def run_clustering(state: AppState, run_id: str) -> dict[str, Any]:
    async with state.sm() as s:
        run = await s.get(Run, run_id)
        if run is None:
            raise LookupError(f"run {run_id} not found")
        roles = run.role_settings
        failures = await _load_failures(s, run_id)
    gateway = _Metered(gateway_for_roles(state.gateway, roles))
    cfg = state.settings

    vectors: list[list[float]] = []
    if failures:
        embed_gw = gateway if cfg.cluster_embedder == "gateway" else None
        vectors = await embed_texts([f.text for f in failures], embed_gw)  # type: ignore[arg-type]
        assert all(len(v) == EMBED_DIM for v in vectors)
    labels = group_failures(vectors, [f.failed for f in failures]) if failures else []
    for f in failures:
        f.attribution = await attribute_episode(
            f.traj,
            f.checks,
            f.verdicts,
            gateway=gateway,  # type: ignore[arg-type]
            attribute_with_llm=cfg.attribute_with_llm,
        )

    rows: list[FailureCluster] = []
    for label in sorted({v for v in labels if v >= 0}):
        idx = [i for i, v in enumerate(labels) if v == label]
        ordered = _centroid_order(vectors, idx)
        members = [failures[i] for i in ordered]
        ids = sorted(m.episode_id for m in members)
        cause, share, why = cluster_root_cause(
            [m.attribution.cause for m in members if m.attribution]
        )
        common = Counter(c for m in members for c in set(m.failed)).most_common(1)
        fallback = f"Cluster {label}: {common[0][0] if common else 'failures'}"
        named = await name_cluster(
            [Exemplar(m.episode_id, m.text) for m in members[:EXEMPLARS]],
            gateway,  # type: ignore[arg-type]
            fallback=fallback,
            member_ids=ids,
            cache=NAMES,
        )
        sev = [m.severity() for m in members]
        rows.append(
            FailureCluster(
                id=new_id("fcl"),
                run_id=run_id,
                label=label,
                name=named.name,
                description=(named.description + (" " if named.description and why else "") + why),
                suspected_cause=named.suspected_cause,
                root_cause=cause,
                root_cause_share=share,
                max_severity=max(sev, key=lambda v: SEVERITY_ORDER[v]) if sev else None,  # type: ignore[arg-type]
                member_episode_ids=ids,
                scenario_ids=sorted({m.scenario.id for m in members}),
                exemplar_episode_id=members[0].episode_id,
            )
        )

    async with state.sm() as s:
        await s.execute(delete(FailureCluster).where(FailureCluster.run_id == run_id))
        await s.execute(delete(FailureEmbedding).where(FailureEmbedding.run_id == run_id))
        for f, v in zip(failures, vectors, strict=True):
            s.add(
                FailureEmbedding(
                    episode_id=f.episode_id,
                    run_id=run_id,
                    embedding=v,
                    text_hash=hashlib.sha256(f.text.encode()).hexdigest(),
                )
            )
        s.add_all(rows)
        await s.commit()
    return {
        "run_id": run_id,
        "failed_episodes": len(failures),
        "clusters": len(rows),
        "unclustered": sum(1 for v in labels if v < 0),
        "cost_usd_micros": gateway.usd,
    }


@handler("cluster")
async def cluster_job(ctx: JobContext) -> dict[str, Any]:
    return await run_clustering(ctx.state, str(ctx.payload["run_id"]))
