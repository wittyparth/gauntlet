"""CI gates (P3-4): a small YAML file turns a run report (and an optional comparison) into
pass, fail or error. Pure functions; every threshold comes from the config, none is invented
here. Uncalibrated rubric dimensions can never fail a gate (hard-cores 5.4)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from .eval.compare import CompareReport
from .eval.report import RunReport

__all__ = [
    "FindingsDelta",
    "GateConfig",
    "GateConfigError",
    "GateOutcome",
    "GateResult",
    "evaluate_gates",
    "load_gates",
]

GateStatus = Literal["pass", "fail", "warn", "skip"]
Mode = Literal["fail", "warn", "pass"]
_SEVERITIES = ("critical", "high", "medium", "low")


class GateConfigError(ValueError):
    pass


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PassRateGate(_M):
    min: float | None = None


class RegressionGate(_M):
    fail_on: list[Literal["regression", "inconclusive", "improvement"]] = ["regression"]
    warn_on: list[Literal["regression", "inconclusive", "improvement"]] = ["inconclusive"]


class SecurityGate(_M):
    max_new_findings: dict[Literal["critical", "high", "medium", "low"], int | None] = {
        "critical": 0,
        "high": None,
    }


class PassHatK(_M):
    k: int = 3
    min: float | None = None


class ReliabilityGate(_M):
    pass_hat_k: PassHatK = PassHatK()


class CostGate(_M):
    max_usd_per_episode: float | None = None
    max_increase_pct: float | None = None


class LatencyGate(_M):
    max_p95_ms: int | None = None


class RubricsGate(_M):
    min_score: float | None = 0.9
    only_calibrated: bool = True


class Gates(_M):
    pass_rate: PassRateGate = PassRateGate()
    regression: RegressionGate = RegressionGate()
    security: SecurityGate = SecurityGate()
    reliability: ReliabilityGate = ReliabilityGate()
    cost: CostGate = CostGate()
    latency: LatencyGate = LatencyGate()
    rubrics: RubricsGate = RubricsGate()


class GateConfig(_M):
    gates: Gates = Gates()
    inconclusive: Mode = "warn"


class FindingsDelta(_M):
    """New findings of the run's agent version versus the baseline's, counted per severity."""

    new_by_severity: dict[str, int] = {}


class GateOutcome(_M):
    id: str
    status: GateStatus
    value: float | str | None = None
    threshold: float | str | None = None
    detail: str = ""


class GateResult(_M):
    passed: bool
    status: Literal["pass", "fail", "error"]
    gates: list[GateOutcome]


def load_gates(path: str | Path | None) -> GateConfig:
    """Defaults when `path` is None. Unknown keys and bad values raise `GateConfigError`."""
    if path is None:
        return GateConfig()
    try:
        raw = yaml.safe_load(Path(path).read_text())
    except (OSError, yaml.YAMLError) as e:
        raise GateConfigError(f"{path}: {e}") from e
    if raw is None:
        return GateConfig()
    if not isinstance(raw, dict):
        raise GateConfigError(f"{path}: top level must be a mapping")
    try:
        return GateConfig.model_validate(raw)
    except ValidationError as e:
        first = e.errors()[0]
        loc = ".".join(str(p) for p in first["loc"])
        raise GateConfigError(f"{path}: {loc}: {first['msg']}") from e


def _regression(cfg: GateConfig, compare: CompareReport | None) -> GateOutcome:
    g = cfg.gates.regression
    if compare is None:
        return GateOutcome(id="regression", status="skip", detail="no baseline")
    verdict = compare.verdict
    status: GateStatus = "pass"
    if verdict == "inconclusive":  # the top-level mode governs; fail_on may only tighten it
        status = "fail" if verdict in g.fail_on else cfg.inconclusive
    elif verdict in g.fail_on:
        status = "fail"
    elif verdict in g.warn_on:
        status = "warn"
    return GateOutcome(
        id="regression", status=status, value=verdict, detail=f"delta {compare.delta:+.3f}"
    )


def _security(cfg: GateConfig, delta: FindingsDelta | None) -> list[GateOutcome]:
    limits = {k: v for k, v in cfg.gates.security.max_new_findings.items() if v is not None}
    if not limits:
        return []
    if delta is None:
        return [GateOutcome(id="security", status="skip", detail="no baseline findings")]
    out = []
    for sev in _SEVERITIES:
        if sev not in limits:
            continue
        n = delta.new_by_severity.get(sev, 0)
        out.append(
            GateOutcome(
                id=f"security.{sev}",
                status="fail" if n > limits[sev] else "pass",  # type: ignore[operator]
                value=float(n),
                threshold=float(limits[sev]),  # type: ignore[arg-type]
                detail=f"{n} new {sev} finding(s)",
            )
        )
    return out


def evaluate_gates(
    config: GateConfig,
    report: RunReport,
    compare: CompareReport | None = None,
    findings_delta: FindingsDelta | None = None,
    *,
    run_status: str = "done",
) -> GateResult:
    """`run_status` other than `done` (cancelled, budget_exhausted, failed...) or a run with no
    counted episodes is `error`, not `fail`: the platform could not produce an answer."""
    g = config.gates
    if run_status != "done" or report.counted == 0:
        why = f"run status {run_status}" if run_status != "done" else "zero counted episodes"
        return GateResult(
            passed=False,
            status="error",
            gates=[GateOutcome(id="run", status="fail", detail=why)],
        )
    out: list[GateOutcome] = []

    if g.pass_rate.min is not None:
        v = report.pass_rate
        out.append(
            GateOutcome(
                id="pass_rate",
                status="skip" if v is None else ("pass" if v >= g.pass_rate.min else "fail"),
                value=v,
                threshold=g.pass_rate.min,
            )
        )
    out.append(_regression(config, compare))
    out.extend(_security(config, findings_delta))

    hk = g.reliability.pass_hat_k
    if hk.min is not None:
        pt = next((p for p in report.reliability if p.k == hk.k), None)
        if pt is None:
            out.append(
                GateOutcome(
                    id="reliability", status="skip", detail=f"no pass^{hk.k} (too few reps)"
                )
            )
        else:
            out.append(
                GateOutcome(
                    id="reliability",
                    status="pass" if pt.value >= hk.min else "fail",
                    value=pt.value,
                    threshold=hk.min,
                    detail=f"pass^{hk.k}",
                )
            )

    if g.cost.max_usd_per_episode is not None:
        usd = report.cost_per_episode_usd_micros / 1_000_000
        out.append(
            GateOutcome(
                id="cost.per_episode",
                status="pass" if usd <= g.cost.max_usd_per_episode else "fail",
                value=usd,
                threshold=g.cost.max_usd_per_episode,
            )
        )
    if g.cost.max_increase_pct is not None:
        pct = compare.cost.delta_pct if compare is not None else None
        out.append(
            GateOutcome(
                id="cost.increase",
                status="skip"
                if pct is None
                else ("pass" if pct <= g.cost.max_increase_pct else "fail"),
                value=pct,
                threshold=g.cost.max_increase_pct,
                detail="no baseline" if compare is None else "",
            )
        )
    if g.latency.max_p95_ms is not None:
        p95 = report.latency_p95_ms
        out.append(
            GateOutcome(
                id="latency.p95",
                status="skip"
                if p95 is None
                else ("pass" if p95 <= g.latency.max_p95_ms else "fail"),
                value=None if p95 is None else float(p95),
                threshold=float(g.latency.max_p95_ms),
            )
        )

    if g.rubrics.min_score is not None:
        for d in report.dimensions:
            gid = f"rubrics.{d.criterion}"
            if g.rubrics.only_calibrated and not d.gating_allowed:
                out.append(GateOutcome(id=gid, status="skip", detail="not calibrated"))
            elif d.score is None:
                out.append(GateOutcome(id=gid, status="skip", detail="no score"))
            else:
                out.append(
                    GateOutcome(
                        id=gid,
                        status="pass" if d.score >= g.rubrics.min_score else "fail",
                        value=d.score,
                        threshold=g.rubrics.min_score,
                    )
                )

    failed = any(o.status == "fail" for o in out)
    return GateResult(
        passed=not failed,
        status="fail" if failed else "pass",
        gates=out,
    )
