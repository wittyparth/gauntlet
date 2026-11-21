import pytest
from gauntlet_core.eval import ParetoPoint, pareto_frontier


def pt(rid, rate, cost, lo=None, hi=None, lat=None):
    return ParetoPoint(
        run_id=rid, agent_version_id="v" + rid, label=rid, pass_rate=rate,
        ci_low=rate - 0.02 if lo is None else lo, ci_high=rate + 0.02 if hi is None else hi,
        cost_per_episode_usd_micros=cost, latency_p95_ms=lat,
    )  # fmt: skip


def by(res):
    return {r.run_id: r for r in res}


def test_frontier_membership():
    r = by(
        pareto_frontier(
            [pt("a", 0.9, 100), pt("b", 0.8, 50), pt("c", 0.7, 200)], ["pass_rate", "cost"]
        )
    )
    assert r["a"].on_frontier and r["b"].on_frontier
    assert not r["c"].on_frontier and r["c"].dominated_by == ["a", "b"]


def test_single_point_and_ties():
    (only,) = pareto_frontier([pt("a", 0.9, 100)], ["pass_rate", "cost"])
    assert only.on_frontier and only.dominated_by == []
    r = by(pareto_frontier([pt("a", 0.9, 100), pt("b", 0.9, 100)], ["pass_rate", "cost"]))
    assert r["a"].on_frontier and r["b"].on_frontier  # equal everywhere: no strict improvement


def test_dominance_supported_only_when_intervals_are_apart():
    close = by(pareto_frontier([pt("a", 0.90, 100), pt("b", 0.88, 200)], ["pass_rate", "cost"]))
    assert close["b"].dominated_by == ["a"] and not close["b"].dominance_supported
    far = by(
        pareto_frontier(
            [pt("a", 0.95, 100, 0.92, 0.97), pt("b", 0.60, 200, 0.55, 0.65)], ["pass_rate", "cost"]
        )
    )
    assert far["b"].dominance_supported and not far["a"].dominance_supported


def test_metric_selection_changes_frontier():
    pts = [pt("a", 0.9, 100, lat=900), pt("b", 0.9, 100, lat=300)]
    assert all(r.on_frontier for r in pareto_frontier(pts, ["pass_rate", "cost"]))
    r = by(pareto_frontier(pts, ["pass_rate", "cost", "latency_p95"]))
    assert r["b"].on_frontier and r["a"].dominated_by == ["b"]
    r1 = by(pareto_frontier([pt("a", 0.9, 100), pt("b", 0.5, 10)], ["pass_rate"]))
    assert r1["a"].on_frontier and not r1["b"].on_frontier


def test_bad_metrics_rejected():
    with pytest.raises(ValueError):
        pareto_frontier([pt("a", 0.9, 1)], ["nope"])
