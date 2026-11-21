"""Run comparison (P3-1): paired statistics from `gauntlet_core.stats`, plus the plain bookkeeping
around them (what was paired and what was not, representative episodes, cost and latency)."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict

from gauntlet_core.schema import SCORED_OUTCOMES
from gauntlet_core.stats import compare_runs as stats_compare
from gauntlet_core.stats import flip_table

from .report import EpisodeRecord, RunReport

__all__ = [
    "CompareReport",
    "CostDelta",
    "DimensionDelta",
    "Flip",
    "LatencyDelta",
    "RunData",
    "compare_runs",
    "comparison_seed",
]

FlipStatus = Literal["newly_failing", "newly_passing", "flaky", "stable"]
_ORDER = {"newly_failing": 0, "newly_passing": 1, "flaky": 2, "stable": 3}


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Flip(_M):
    scenario_id: str
    title: str
    status: FlipStatus
    rate_baseline: float
    rate_run: float
    n_baseline: int
    n_run: int
    p_value: float | None = None
    single_trial: bool = False
    episode_baseline: str | None = None
    episode_run: str | None = None


class DimensionDelta(_M):
    criterion: str
    severity: Literal["low", "medium", "high", "critical"]
    score_baseline: float
    score_run: float
    delta: float
    gating_allowed: bool


class CostDelta(_M):
    baseline_per_episode_usd_micros: int
    run_per_episode_usd_micros: int
    delta_pct: float | None


class LatencyDelta(_M):
    p50_baseline_ms: int | None
    p50_run_ms: int | None
    p95_baseline_ms: int | None
    p95_run_ms: int | None


class CompareParams(_M):
    resamples: int
    seed: int


class CompareReport(_M):
    run_id: str
    baseline_id: str
    suite_id: str
    margin: float
    verdict: Literal["regression", "improvement", "no_detectable_change", "inconclusive"]
    delta: float
    ci_low: float
    ci_high: float
    p_value: float
    detectable_effect_text: str | None
    shared_scenarios: int
    only_in_run: list[str]
    only_in_baseline: list[str]
    flips: list[Flip]
    dimension_deltas: list[DimensionDelta]
    cost: CostDelta
    latency: LatencyDelta
    cautions: list[str]
    params: CompareParams


@dataclass(frozen=True)
class RunData:
    run_id: str
    suite_id: str
    scenario_versions: dict[str, int]
    records: list[EpisodeRecord]
    report: RunReport
    agent_label: str
    model: str | None
    quarantined: frozenset[str] = frozenset()
    rubric_versions: dict[str, int] = field(default_factory=dict)
    repetitions: int | None = None
    judge_model: str | None = None
    agent_id: str | None = None


def comparison_seed(run_id: str, baseline_id: str) -> int:
    return int.from_bytes(hashlib.sha256((run_id + baseline_id).encode()).digest()[:8], "big")


def _trials(records: Sequence[EpisodeRecord], keep: set[str]) -> dict[str, list[EpisodeRecord]]:
    out: dict[str, list[EpisodeRecord]] = defaultdict(list)
    for r in sorted(records, key=lambda r: (r.scenario_id, r.rep)):
        if r.scenario_id in keep and r.outcome in SCORED_OUTCOMES:
            out[r.scenario_id].append(r)
    return out


def _pick(recs: list[EpisodeRecord], want_pass: bool | None) -> str | None:
    """Earliest rep with the wanted outcome (any outcome when `want_pass` is None)."""
    for r in recs:
        if want_pass is None or (r.outcome == "passed") == want_pass:
            return r.episode_id
    return recs[0].episode_id if recs else None


def _representatives(
    status: FlipStatus, a: list[EpisodeRecord], b: list[EpisodeRecord]
) -> tuple[str | None, str | None]:
    if status == "newly_failing":
        return _pick(a, True), _pick(b, False)
    if status == "newly_passing":
        return _pick(a, False), _pick(b, True)
    return _pick(a, None), _pick(b, None)


def _pct(base: int, run: int) -> float | None:
    return round((run - base) / base * 100, 2) if base > 0 else None


def compare_runs(
    a: RunData,
    b: RunData,
    *,
    margin: float = 0.02,
    seed: int | None = None,
    resamples: int = 2000,
) -> CompareReport:
    """`a` is the baseline, `b` the candidate. `seed` defaults to the spec's derivation from the
    two run ids, so repeated calls give identical numbers."""
    seed = comparison_seed(b.run_id, a.run_id) if seed is None else seed
    cautions: list[str] = []
    candidates = set(a.scenario_versions) & set(b.scenario_versions)
    keep: set[str] = set()
    for sid in sorted(candidates):
        if sid in a.quarantined or sid in b.quarantined:
            cautions.append(f"quarantined:{sid}")
        elif a.scenario_versions[sid] != b.scenario_versions[sid] or _rubrics_differ(a, b):
            cautions.append(f"version_mismatch:{sid}")
        else:
            keep.add(sid)
    ra, rb = _trials(a.records, keep), _trials(b.records, keep)
    paired = {s for s in keep if ra.get(s) and rb.get(s)}
    data_a = {s: [r.outcome == "passed" for r in ra[s]] for s in paired}
    data_b = {s: [r.outcome == "passed" for r in rb[s]] for s in paired}
    cmp = stats_compare(data_a, data_b, margin=margin, resamples=resamples, seed=seed)

    titles = {s.scenario_id: s.title for s in b.report.per_scenario}
    flips = []
    for f in flip_table(data_a, data_b):
        status: FlipStatus = f.category
        ep_a, ep_b = _representatives(status, ra[f.scenario_id], rb[f.scenario_id])
        flips.append(
            Flip(
                scenario_id=f.scenario_id,
                title=titles.get(f.scenario_id, f.scenario_id),
                status=status,
                rate_baseline=f.rate_a,
                rate_run=f.rate_b,
                n_baseline=len(data_a[f.scenario_id]),
                n_run=len(data_b[f.scenario_id]),
                p_value=f.p_value,
                single_trial=f.note == "single trial",
                episode_baseline=ep_a,
                episode_run=ep_b,
            )
        )
    flips.sort(key=lambda f: (_ORDER[f.status], f.scenario_id))

    if a.repetitions and b.repetitions and a.repetitions != b.repetitions:
        cautions.append(f"repetitions_differ:{a.repetitions}/{b.repetitions}")
    if a.judge_model != b.judge_model:
        cautions.append(f"judge_model_differs:{a.judge_model}/{b.judge_model}")
    if a.agent_id and b.agent_id and a.agent_id != b.agent_id:
        cautions.append("different_agents")
    if a.agent_label != b.agent_label:
        cautions.append(f"agent_versions:{a.agent_label} -> {b.agent_label}")

    base_dims = {d.criterion: d for d in a.report.dimensions}
    dims = [
        DimensionDelta(
            criterion=d.criterion,
            severity=d.severity,
            score_baseline=base_dims[d.criterion].score,  # type: ignore[arg-type]
            score_run=d.score,  # type: ignore[arg-type]
            delta=round(d.score - base_dims[d.criterion].score, 6),  # type: ignore[operator]
            gating_allowed=d.gating_allowed and base_dims[d.criterion].gating_allowed,
        )
        for d in b.report.dimensions
        if d.criterion in base_dims
        and d.score is not None
        and base_dims[d.criterion].score is not None
    ]
    verdict = cmp.verdict.replace(" ", "_")
    return CompareReport(
        run_id=b.run_id,
        baseline_id=a.run_id,
        suite_id=b.suite_id,
        margin=margin,
        verdict=verdict,  # type: ignore[arg-type]
        delta=cmp.delta.value,
        ci_low=cmp.delta.low,
        ci_high=cmp.delta.high,
        p_value=cmp.p_value,
        detectable_effect_text=cmp.message if verdict == "inconclusive" else None,
        shared_scenarios=len(paired),
        only_in_run=sorted(set(b.scenario_versions) - set(a.scenario_versions)),
        only_in_baseline=sorted(set(a.scenario_versions) - set(b.scenario_versions)),
        flips=flips,
        dimension_deltas=dims,
        cost=CostDelta(
            baseline_per_episode_usd_micros=a.report.cost_per_episode_usd_micros,
            run_per_episode_usd_micros=b.report.cost_per_episode_usd_micros,
            delta_pct=_pct(
                a.report.cost_per_episode_usd_micros, b.report.cost_per_episode_usd_micros
            ),
        ),
        latency=LatencyDelta(
            p50_baseline_ms=a.report.latency_p50_ms,
            p50_run_ms=b.report.latency_p50_ms,
            p95_baseline_ms=a.report.latency_p95_ms,
            p95_run_ms=b.report.latency_p95_ms,
        ),
        cautions=cautions,
        params=CompareParams(resamples=resamples, seed=seed),
    )


def _rubrics_differ(a: RunData, b: RunData) -> bool:
    shared = set(a.rubric_versions) & set(b.rubric_versions)
    return any(a.rubric_versions[r] != b.rubric_versions[r] for r in shared)
