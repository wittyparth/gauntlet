"""Calibration (03-hard-cores 5.4): pick tau and decide whether a rubric may gate CI."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from gauntlet_core.llm.gateway import Gateway
from gauntlet_core.schema import Rubric, Trajectory
from gauntlet_core.stats import Agreement, judge_agreement

from .cascade import SMALL_ROLE, STRONG_ROLE, StageResult, accept_small, run_stage

DEFAULT_TAUS: tuple[float, ...] = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.01)  # 1.01 = always escalate
KAPPA_TOLERANCE = 0.03
GATE_MIN_KAPPA = 0.6
GATE_MIN_ITEMS = 40
GATE_MIN_PER_CLASS = 10


@dataclass(frozen=True)
class GoldenItem:
    id: str
    trajectory: Trajectory
    human: Literal["pass", "fail", "na"]


@dataclass(frozen=True)
class TauPoint:
    tau: float
    agreement: Agreement | None
    escalation_rate: float
    cost_per_verdict_usd_micros: float
    n_errors: int


@dataclass(frozen=True)
class CalibrationReport:
    rubric_id: str
    n: int
    n_fail: int
    n_nonfail: int
    small: Agreement | None
    strong: Agreement | None
    points: list[TauPoint]
    threshold: float
    gating_allowed: bool
    gating_reason: str


def calibrated(rubric: Rubric, report: CalibrationReport) -> Rubric:
    return rubric.model_copy(
        update={"threshold": min(report.threshold, 1.0), "gating_allowed": report.gating_allowed}
    )


def _agreement(pred: list[bool], human: list[bool], resamples: int) -> Agreement | None:
    return judge_agreement(pred, human, resamples=resamples) if pred else None


async def calibrate(
    rubric: Rubric,
    golden: Sequence[GoldenItem],
    gateway: Gateway,
    *,
    taus: Sequence[float] = DEFAULT_TAUS,
    policy_text: str = "",
    small_role: str = SMALL_ROLE,
    strong_role: str = STRONG_ROLE,
    resamples: int = 1000,
) -> CalibrationReport:
    """Runs the small and strong judge once per item (2 calls plus retries), then evaluates the
    cascade at every tau offline from those outputs: no extra calls per tau."""
    smalls: list[StageResult] = []
    strongs: list[StageResult] = []
    for item in golden:
        smalls.append(
            await run_stage(gateway, small_role, rubric, item.trajectory, policy_text=policy_text)
        )
        strongs.append(
            await run_stage(gateway, strong_role, rubric, item.trajectory, policy_text=policy_text)
        )
    human = [g.human == "fail" for g in golden]

    def fail_of(s: StageResult) -> bool:
        assert s.output is not None
        return s.output.result == "fail"

    s_idx = [i for i, s in enumerate(smalls) if s.valid]
    t_idx = [i for i, s in enumerate(strongs) if s.valid]
    small_ag = _agreement([fail_of(smalls[i]) for i in s_idx], [human[i] for i in s_idx], resamples)
    strong_ag = _agreement(
        [fail_of(strongs[i]) for i in t_idx], [human[i] for i in t_idx], resamples
    )

    points: list[TauPoint] = []
    for tau in sorted(taus):
        pred: list[bool] = []
        hum: list[bool] = []
        escalated = 0
        errors = 0
        cost = 0
        for i in range(len(golden)):
            cost += smalls[i].cost.usd_micros
            if accept_small(rubric.severity, smalls[i], tau):
                pred.append(fail_of(smalls[i]))
                hum.append(human[i])
                continue
            escalated += 1
            cost += strongs[i].cost.usd_micros
            if strongs[i].valid:
                pred.append(fail_of(strongs[i]))
                hum.append(human[i])
            else:
                errors += 1
        n = max(len(golden), 1)
        points.append(
            TauPoint(tau, _agreement(pred, hum, resamples), escalated / n, cost / n, errors)
        )

    threshold = max(taus) if taus else 1.0
    if strong_ag is not None:
        for p in points:
            if p.agreement is not None and p.agreement.kappa >= strong_ag.kappa - KAPPA_TOLERANCE:
                threshold = p.tau
                break

    n_fail = sum(human)
    n_nonfail = len(human) - n_fail
    reasons = []
    if strong_ag is None or strong_ag.kappa < GATE_MIN_KAPPA:
        k = "n/a" if strong_ag is None else f"{strong_ag.kappa:.2f}"
        reasons.append(f"strong-judge kappa {k} < {GATE_MIN_KAPPA}")
    if len(golden) < GATE_MIN_ITEMS:
        reasons.append(f"{len(golden)} labelled items < {GATE_MIN_ITEMS}")
    if n_fail < GATE_MIN_PER_CLASS or n_nonfail < GATE_MIN_PER_CLASS:
        reasons.append(f"classes {n_fail}/{n_nonfail} below {GATE_MIN_PER_CLASS} each")
    return CalibrationReport(
        rubric_id=rubric.id,
        n=len(golden),
        n_fail=n_fail,
        n_nonfail=n_nonfail,
        small=small_ag,
        strong=strong_ag,
        points=points,
        threshold=threshold,
        gating_allowed=not reasons,
        gating_reason="; ".join(reasons) or "ok",
    )
