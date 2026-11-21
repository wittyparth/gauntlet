from check_helpers import scenario
from gauntlet_core.eval import EpisodeRecord, aggregate_run

SCN = {s: scenario().model_copy(update={"id": s, "title": s.upper()}) for s in ("a", "b", "c", "q")}


def eps(sid, outcomes):
    return [
        EpisodeRecord(f"{sid}{i}", sid, i, o, None, 100, 1000, "full")
        for i, o in enumerate(outcomes)
    ]


def test_phase1_fields_unchanged_and_new_fields_default_empty():
    r = aggregate_run("r", eps("a", ["passed", "failed"]), {}, SCN, seed=1)
    assert r.quarantined == [] and not r.caution.adaptive_sampling
    s = r.per_scenario[0]
    assert (s.flaky, s.flakiness, s.quarantined, s.posterior_mean) == (False, None, False, None)
    assert [p.k for p in r.reliability] == [1, 2]


def test_reliability_and_flaky_flags():
    e = eps("a", ["passed"] * 5) + eps("b", ["passed", "passed", "failed", "passed", "failed"])
    r = aggregate_run("r", e, {}, SCN, seed=1)
    assert [p.k for p in r.reliability] == [1, 2, 3, 4, 5]
    assert r.pass_rate is not None and abs(r.reliability[0].value - r.pass_rate) < 1e-9
    a, b = r.per_scenario
    assert not a.flaky and b.flaky and b.flakiness is not None and abs(b.flakiness - 0.8) < 1e-9


def test_quarantined_excluded_from_headline_and_listed_with_own_rate():
    e = eps("a", ["passed"] * 3) + eps("q", ["failed"] * 3)
    r = aggregate_run("r", e, {}, SCN, seed=1, quarantined={"q"})
    assert r.pass_rate == 1.0 and r.counted == 3 and r.quarantined == ["q"]
    q = next(s for s in r.per_scenario if s.scenario_id == "q")
    assert q.quarantined and q.rate == 0.0 and q.counted == 3
    assert [p.scenarios for p in r.reliability] == [1, 1, 1]
    assert r.cost_usd_micros == 600  # money was still spent


def test_adaptive_uses_posterior_means_for_early_stops_and_sets_the_caution():
    e = eps("a", ["passed"] * 3) + eps("b", ["passed", "failed", "passed", "failed", "passed"])
    r = aggregate_run("r", e, {}, SCN, seed=1, adaptive=True, repetitions=5)
    assert r.caution.adaptive_sampling
    a, b = r.per_scenario
    assert a.posterior_mean == (3 + 1) / (3 + 2) and a.rate == a.posterior_mean
    assert a.rate is not None and a.ci_low is not None and a.ci_high is not None
    assert a.ci_low < a.rate < a.ci_high
    assert b.posterior_mean is None and b.rate == 0.6  # ran to the maximum: naive rate
    assert r.pass_rate is not None and abs(r.pass_rate - ((a.posterior_mean or 0) + 0.6) / 2) < 1e-9


def test_human_overridden_counts_only_counted_episodes():
    e = eps("a", ["passed", "failed"]) + eps("b", ["budget_exhausted"])
    r = aggregate_run("r", e, {}, SCN, seed=1, human_overridden={"a0", "b0", "zzz"})
    assert r.human_overridden == 1
    assert aggregate_run("r", e, {}, SCN, seed=1).human_overridden == 0
