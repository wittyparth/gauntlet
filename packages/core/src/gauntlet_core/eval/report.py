"""Run report models and aggregation (CQ-B7). Statistics come from `gauntlet_core.stats`."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from gauntlet_core.judges import model_family
from gauntlet_core.schema import SCORED_OUTCOMES, SEVERITY_ORDER, Rubric, Scenario, Verdict
from gauntlet_core.stats import (
    beta_credible_interval,
    posterior_mean,
    suite_pass_rate,
    wilson_estimate,
)

from .reliability import ReliabilityPoint, reliability_curve
from .scoring import composite_score, dimension_score, hard_fail_episodes
from .stability import classify_flaky

__all__ = [
    "Caution",
    "DimensionStats",
    "EpisodeRecord",
    "FailureRef",
    "ReliabilityPoint",
    "RunReport",
    "ScenarioStats",
    "aggregate_run",
    "percentile_nearest_rank",
]

RESAMPLES = 2000


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScenarioStats(_M):
    scenario_id: str
    title: str
    counted: int
    passed: int
    rate: float | None
    ci_low: float | None
    ci_high: float | None
    excluded: dict[str, int]
    episode_ids: list[str]
    flaky: bool = False
    flakiness: float | None = None
    quarantined: bool = False
    posterior_mean: float | None = None  # adaptive runs: set for scenarios that stopped early


class DimensionStats(_M):
    criterion: str
    severity: Literal["low", "medium", "high", "critical"]
    passed: int
    failed: int
    na: int
    error: int
    score: float | None
    gating_allowed: bool


class FailureRef(_M):
    episode_id: str
    scenario_id: str
    reasons: list[str]


class Caution(_M):
    self_preference: bool
    uncalibrated_rubrics: list[str]
    world_fidelity: Literal["full", "simulated"]
    reduced_coverage: bool
    unpriced_models: list[str]
    adaptive_sampling: bool = False


class RunReport(_M):
    run_id: str
    counted: int
    excluded: dict[str, int]
    pass_rate: float | None
    ci_low: float | None
    ci_high: float | None
    per_scenario: list[ScenarioStats]
    dimensions: list[DimensionStats]
    composite_score: float | None
    hard_fail_episodes: list[str]
    cost_usd_micros: int
    cost_per_episode_usd_micros: int
    latency_p50_ms: int | None
    latency_p95_ms: int | None
    failures: list[FailureRef]
    caution: Caution
    reliability: list[ReliabilityPoint] = []
    quarantined: list[str] = []


@dataclass(frozen=True)
class EpisodeRecord:
    episode_id: str
    scenario_id: str
    rep: int
    outcome: str
    termination: str | None
    cost_usd_micros: int
    latency_ms: int
    world_fidelity: str
    reasons: tuple[str, ...] = ()


def percentile_nearest_rank(values: Sequence[int], q: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(1, math.ceil(q * len(ordered))) - 1]


def _dimensions(
    verdicts: Mapping[str, Sequence[Verdict]],
    counted_ids: set[str],
    rubrics: Mapping[str, Rubric] | None,
) -> list[DimensionStats]:
    tally: dict[str, Counter[str]] = defaultdict(Counter)
    severity: dict[str, str] = {}
    for ep, vs in verdicts.items():
        if ep not in counted_ids:
            continue
        for v in vs:
            tally[v.criterion][v.result] += 1
            severity.setdefault(v.criterion, v.severity)
    out = []
    for crit in sorted(tally):
        t = tally[crit]
        rub = (rubrics or {}).get(crit)
        out.append(
            DimensionStats(
                criterion=crit,
                severity=severity[crit],  # type: ignore[arg-type]
                passed=t["pass"],
                failed=t["fail"],
                na=t["na"],
                error=t["error"],
                score=dimension_score(t["pass"], t["fail"]),
                gating_allowed=bool(rub and rub.gating_allowed),
            )
        )
    return out


def _failures(
    failed: Sequence[EpisodeRecord],
    verdicts: Mapping[str, Sequence[Verdict]],
    scenarios: Mapping[str, Scenario],
) -> list[FailureRef]:
    def sev(rec: EpisodeRecord, reason: str) -> int:
        scn = scenarios.get(rec.scenario_id)
        for nc in scn.forbidden if scn else []:
            if nc.id == reason:
                return SEVERITY_ORDER[nc.severity]
        return SEVERITY_ORDER["high"] if reason == "success" else SEVERITY_ORDER["medium"]

    rows: list[tuple[int, FailureRef]] = []
    for rec in failed:
        hard = [
            v.criterion
            for v in verdicts.get(rec.episode_id, ())
            if v.result == "fail" and v.hard_fail
        ]
        reasons = [*rec.reasons, *(h for h in hard if h not in rec.reasons)]
        levels = [sev(rec, r) for r in rec.reasons]
        if hard:
            levels.append(SEVERITY_ORDER["critical"])
        top = max(levels, default=0)
        rows.append(
            (
                top,
                FailureRef(episode_id=rec.episode_id, scenario_id=rec.scenario_id, reasons=reasons),
            )
        )
    rows.sort(key=lambda r: (-r[0], r[1].episode_id))
    return [r for _, r in rows]


def aggregate_run(
    run_id: str,
    episodes: Sequence[EpisodeRecord],
    verdicts: Mapping[str, Sequence[Verdict]],
    scenarios: Mapping[str, Scenario],
    *,
    seed: int,
    judge_model: str | None = None,
    target_model: str | None = None,
    target_kind: str = "hosted",
    wired: bool = False,
    rubrics: Mapping[str, Rubric] | None = None,
    unpriced_models: Sequence[str] = (),
    quarantined: Collection[str] = (),
    adaptive: bool = False,
    repetitions: int | None = None,
) -> RunReport:
    """`quarantined` scenarios are reported with their own rate but excluded from every
    headline number. `adaptive` runs report posterior means (and Beta credible intervals) for
    scenarios that stopped before `repetitions`, because early stopping biases naive rates."""
    quarantine = set(quarantined)
    headline = [e for e in episodes if e.scenario_id not in quarantine]
    counted_eps = [e for e in headline if e.outcome in SCORED_OUTCOMES]
    excluded = dict(Counter(e.outcome for e in headline if e.outcome not in SCORED_OUTCOMES))

    by_scn: dict[str, list[EpisodeRecord]] = defaultdict(list)
    for e in episodes:
        by_scn[e.scenario_id].append(e)
    per_scenario: list[ScenarioStats] = []
    data: dict[str, list[bool]] = {}
    early: dict[str, float] = {}  # adaptive scenarios that stopped early: posterior mean
    for sid in sorted(by_scn):
        recs = by_scn[sid]
        scored = [r for r in recs if r.outcome in SCORED_OUTCOMES]
        passed = sum(1 for r in scored if r.outcome == "passed")
        est = wilson_estimate(passed, len(scored)) if scored else None
        trials = [r.outcome == "passed" for r in scored]
        if scored and sid not in quarantine:
            data[sid] = trials
        rate = est.value if est else None
        lo, hi = (est.low, est.high) if est else (None, None)
        post: float | None = None
        if (
            adaptive
            and repetitions
            and scored
            and sid not in quarantine
            and len(scored) < repetitions
        ):
            post = posterior_mean(passed, len(scored))
            early[sid] = post
            rate = post
            lo, hi = beta_credible_interval(passed, len(scored))
        flaky = classify_flaky(trials)
        scn = scenarios.get(sid)
        per_scenario.append(
            ScenarioStats(
                scenario_id=sid,
                title=scn.title if scn else sid,
                counted=len(scored),
                passed=passed,
                rate=rate,
                ci_low=lo,
                ci_high=hi,
                excluded=dict(Counter(r.outcome for r in recs if r.outcome not in SCORED_OUTCOMES)),
                episode_ids=[r.episode_id for r in recs],
                flaky=flaky.flaky,
                flakiness=flaky.flakiness,
                quarantined=sid in quarantine,
                posterior_mean=post,
            )
        )

    suite = suite_pass_rate(data, resamples=RESAMPLES, seed=seed) if data else None
    pass_rate, ci_low, ci_high = (
        (suite.value, suite.low, suite.high) if suite else (None, None, None)
    )
    if suite and early:  # posterior means stand in for the naive rate of early stops
        rates = [early.get(sid, sum(t) / len(t)) for sid, t in data.items()]
        pass_rate = sum(rates) / len(rates)
        ci_low, ci_high = min(suite.low, pass_rate), max(suite.high, pass_rate)
    counted_ids = {e.episode_id for e in counted_eps}
    dims = _dimensions(verdicts, counted_ids, rubrics)
    cost = sum(e.cost_usd_micros for e in episodes)
    lat = [e.latency_ms for e in counted_eps]
    uncal = sorted(
        {
            v.criterion
            for vs in verdicts.values()
            for v in vs
            if rubrics is not None
            and v.criterion in rubrics
            and not rubrics[v.criterion].gating_allowed
        }
    )
    self_pref = bool(
        judge_model and target_model and model_family(judge_model) == model_family(target_model)
    )
    return RunReport(
        run_id=run_id,
        counted=len(counted_eps),
        excluded=excluded,
        pass_rate=pass_rate,
        ci_low=ci_low,
        ci_high=ci_high,
        per_scenario=per_scenario,
        dimensions=dims,
        composite_score=composite_score((d.score, d.severity) for d in dims),
        hard_fail_episodes=hard_fail_episodes(
            {k: v for k, v in verdicts.items() if k in counted_ids}
        ),
        cost_usd_micros=cost,
        cost_per_episode_usd_micros=cost // len(episodes) if episodes else 0,
        latency_p50_ms=percentile_nearest_rank(lat, 0.5),
        latency_p95_ms=percentile_nearest_rank(lat, 0.95),
        failures=_failures([e for e in episodes if e.outcome == "failed"], verdicts, scenarios),
        caution=Caution(
            self_preference=self_pref,
            uncalibrated_rubrics=uncal,
            world_fidelity="simulated"
            if any(e.world_fidelity == "simulated" for e in episodes)
            else "full",
            reduced_coverage=target_kind in ("http", "openai_compat") and not wired,
            unpriced_models=sorted(unpriced_models),
            adaptive_sampling=adaptive,
        ),
        reliability=reliability_curve(data, seed=seed, resamples=RESAMPLES),
        quarantined=sorted(q for q in quarantine if q in by_scn),
    )
