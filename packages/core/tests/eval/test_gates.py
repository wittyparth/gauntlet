import pytest
from check_helpers import scenario
from gauntlet_core.eval import DimensionStats, EpisodeRecord, aggregate_run
from gauntlet_core.eval.compare import CompareParams, CompareReport, CostDelta, LatencyDelta
from gauntlet_core.gates import (
    FindingsDelta,
    GateConfig,
    GateConfigError,
    evaluate_gates,
    load_gates,
)

SCN = {"a": scenario().model_copy(update={"id": "a", "title": "A"})}


def report(outcomes=("passed",) * 5, *, cost=100, dims=()):
    eps = [
        EpisodeRecord(f"e{i}", "a", i, o, None, cost, 1000 + i, "full")
        for i, o in enumerate(outcomes)
    ]
    r = aggregate_run("r", eps, {}, SCN, seed=1)
    return r.model_copy(update={"dimensions": list(dims)})


def dim(name, score, gating):
    return DimensionStats(
        criterion=name,
        severity="high",
        passed=9,
        failed=1,
        na=0,
        error=0,
        score=score,
        gating_allowed=gating,
    )


def cmp(verdict, delta_pct=None):
    return CompareReport(
        run_id="r",
        baseline_id="b",
        suite_id="s",
        margin=0.02,
        verdict=verdict,
        delta=-0.1,
        ci_low=-0.2,
        ci_high=0.0,
        p_value=0.04,
        detectable_effect_text="need more reps" if verdict == "inconclusive" else None,
        shared_scenarios=1,
        only_in_run=[],
        only_in_baseline=[],
        flips=[],
        dimension_deltas=[],
        cost=CostDelta(
            baseline_per_episode_usd_micros=100,
            run_per_episode_usd_micros=150,
            delta_pct=delta_pct,
        ),
        latency=LatencyDelta(p50_baseline_ms=1, p50_run_ms=1, p95_baseline_ms=1, p95_run_ms=1),
        cautions=[],
        params=CompareParams(resamples=1, seed=1),
    )


def cfg(**kw):
    return GateConfig.model_validate(kw)


def status(res, gate_id):
    return next(g.status for g in res.gates if g.id == gate_id)


def test_defaults_pass_with_no_inputs():
    res = evaluate_gates(GateConfig(), report())
    assert res.passed and res.status == "pass"
    assert status(res, "regression") == "skip"


def test_pass_rate_truth_table():
    c = cfg(gates={"pass_rate": {"min": 0.8}})
    assert status(evaluate_gates(c, report()), "pass_rate") == "pass"
    bad = report(("passed", "failed", "failed", "failed", "failed"))
    res = evaluate_gates(c, bad)
    assert status(res, "pass_rate") == "fail" and res.status == "fail" and not res.passed


@pytest.mark.parametrize(
    ("verdict", "mode", "expected"),
    [
        ("regression", "warn", "fail"),
        ("improvement", "warn", "pass"),
        ("no_detectable_change", "warn", "pass"),
        ("inconclusive", "warn", "warn"),
        ("inconclusive", "fail", "fail"),
        ("inconclusive", "pass", "pass"),
    ],
)
def test_regression_and_inconclusive_modes(verdict, mode, expected):
    res = evaluate_gates(cfg(inconclusive=mode), report(), cmp(verdict))
    assert status(res, "regression") == expected
    assert res.status == ("fail" if expected == "fail" else "pass")


def test_warn_does_not_fail_the_gate():
    res = evaluate_gates(GateConfig(), report(), cmp("inconclusive"))
    assert res.passed and status(res, "regression") == "warn"


def test_security_gate_new_findings():
    c = cfg(gates={"security": {"max_new_findings": {"critical": 0, "high": 2}}})
    assert status(evaluate_gates(c, report()), "security") == "skip"
    ok = evaluate_gates(c, report(), findings_delta=FindingsDelta(new_by_severity={"high": 2}))
    assert ok.passed
    bad = evaluate_gates(c, report(), findings_delta=FindingsDelta(new_by_severity={"critical": 1}))
    assert status(bad, "security.critical") == "fail" and not bad.passed


def test_reliability_gate():
    c = cfg(gates={"reliability": {"pass_hat_k": {"k": 3, "min": 0.9}}})
    assert status(evaluate_gates(c, report()), "reliability") == "pass"
    assert status(evaluate_gates(c, report(("passed", "passed"))), "reliability") == "skip"
    flaky = report(("passed", "failed", "passed", "failed", "passed"))
    assert status(evaluate_gates(c, flaky), "reliability") == "fail"


def test_cost_and_latency_gates():
    c = cfg(
        gates={
            "cost": {"max_usd_per_episode": 0.0001, "max_increase_pct": 20},
            "latency": {"max_p95_ms": 500},
        }
    )
    res = evaluate_gates(c, report(cost=500), cmp("no_detectable_change", delta_pct=50.0))
    assert status(res, "cost.per_episode") == "fail"
    assert status(res, "cost.increase") == "fail"
    assert status(res, "latency.p95") == "fail"
    res = evaluate_gates(c, report(cost=100))
    assert status(res, "cost.per_episode") == "pass" and status(res, "cost.increase") == "skip"


def test_uncalibrated_rubric_can_never_fail():
    dims = [dim("honest", 0.1, gating=False), dim("polite", 0.5, gating=True)]
    res = evaluate_gates(GateConfig(), report(dims=dims))
    assert status(res, "rubrics.honest") == "skip" and status(res, "rubrics.polite") == "fail"
    only = evaluate_gates(GateConfig(), report(dims=dims[:1]))
    assert only.passed
    off = cfg(gates={"rubrics": {"min_score": 0.9, "only_calibrated": False}})
    assert status(evaluate_gates(off, report(dims=dims[:1])), "rubrics.honest") == "fail"


def test_zero_counted_and_incomplete_runs_are_errors():
    zero = report(("budget_exhausted",))
    assert evaluate_gates(GateConfig(), zero).status == "error"
    for st in ("cancelled", "budget_exhausted", "running"):
        res = evaluate_gates(GateConfig(), report(), run_status=st)
        assert res.status == "error" and not res.passed


def test_load_gates(tmp_path):
    assert load_gates(None) == GateConfig()
    p = tmp_path / "g.yaml"
    p.write_text("gates:\n  pass_rate: {min: 0.7}\ninconclusive: fail\n")
    c = load_gates(p)
    assert c.gates.pass_rate.min == 0.7 and c.inconclusive == "fail"
    p.write_text("gates:\n  bogus: {}\n")
    with pytest.raises(GateConfigError, match="bogus"):
        load_gates(p)
    p.write_text("inconclusive: maybe\n")
    with pytest.raises(GateConfigError):
        load_gates(p)
    with pytest.raises(GateConfigError):
        load_gates(tmp_path / "missing.yaml")
