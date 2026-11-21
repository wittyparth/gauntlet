import math
import random
from itertools import combinations

import pytest
from gauntlet_core.stats import (
    cohens_kappa,
    compare_runs,
    fisher_exact,
    flip_table,
    judge_agreement,
    pass_hat_k,
    posterior_mean,
    reliability_curve,
    sequential_decision,
    sign_flip_pvalue,
    suite_pass_hat_k,
    suite_pass_rate,
    wilson_interval,
)
from gauntlet_core.stats.sequential import beta_cdf
from hypothesis import given, settings
from hypothesis import strategies as st

trials = st.lists(st.booleans(), min_size=1, max_size=8)
suites = st.dictionaries(st.text("abcdef", min_size=1, max_size=3), trials, min_size=1, max_size=6)


# --- Wilson -------------------------------------------------------------------------------


def test_wilson_known_values():
    # Hand computed from the Wilson formula, z = 1.959964.
    lo, hi = wilson_interval(5, 10)
    assert (lo, hi) == pytest.approx((0.2366, 0.7634), abs=1e-4)
    lo, hi = wilson_interval(0, 10)
    assert lo == 0.0 and hi == pytest.approx(0.2775, abs=1e-4)
    lo, hi = wilson_interval(10, 10)
    assert hi == pytest.approx(1.0) and lo == pytest.approx(0.7225, abs=1e-4)
    # Hand computed (81/263): centre 0.31061, half-width 0.05546.
    lo, hi = wilson_interval(81, 263)
    assert (lo, hi) == pytest.approx((0.2552, 0.3661), abs=2e-4)


def test_wilson_empty_is_vacuous():
    assert wilson_interval(0, 0) == (0.0, 1.0)


@given(st.integers(0, 200).flatmap(lambda n: st.tuples(st.integers(0, n), st.just(n))))
def test_wilson_bounds_contain_phat(xn):
    x, n = xn
    lo, hi = wilson_interval(x, n)
    assert 0.0 <= lo <= hi <= 1.0
    if n:
        assert lo - 1e-12 <= x / n <= hi + 1e-12


# --- pass^k -------------------------------------------------------------------------------


@given(trials)
def test_pass_hat_k_matches_brute_force(ts):
    n, c = len(ts), sum(ts)
    for k in range(1, n + 1):
        subsets = list(combinations(ts, k))
        brute = sum(1 for s in subsets if all(s)) / len(subsets)
        assert pass_hat_k(c, n, k) == pytest.approx(brute)


@pytest.mark.parametrize("n,k", [(5, 1), (8, 3), (10, 8)])
def test_pass_hat_k_unbiased_exactly(n, k):
    # E[C(c,k)/C(n,k)] over c ~ Binomial(n, p) equals p**k exactly.
    for p in (0.1, 0.5, 0.9):
        e = sum(
            math.comb(n, c) * p**c * (1 - p) ** (n - c) * pass_hat_k(c, n, k) for c in range(n + 1)
        )
        assert e == pytest.approx(p**k)


def test_pass_hat_k_rejects_bad_k():
    with pytest.raises(ValueError):
        pass_hat_k(1, 3, 4)


@given(suites)
@settings(max_examples=30, deadline=None)
def test_pass1_equals_pass_rate(data):
    rate = suite_pass_rate(data, resamples=50)
    p1 = suite_pass_hat_k(data, 1, resamples=50)
    assert rate.value == pytest.approx(p1.value)
    mean = sum(sum(t) / len(t) for t in data.values()) / len(data)
    assert rate.value == pytest.approx(mean)
    assert 0 <= rate.low <= rate.value <= rate.high <= 1


def test_reliability_curve_is_monotone_and_seeded():
    data = {"a": [True] * 8, "b": [True] * 6 + [False] * 2, "c": [True, False] * 4}
    curve = reliability_curve(data, resamples=200, seed=3)
    assert [p.k for p in curve] == list(range(1, 9))
    values = [p.estimate.value for p in curve]
    assert values == sorted(values, reverse=True)
    assert curve[0].estimate.value == pytest.approx(suite_pass_rate(data, resamples=200).value)
    assert curve == reliability_curve(data, resamples=200, seed=3)


def test_bootstrap_degenerate_suite():
    est = suite_pass_rate({"a": [True] * 4, "b": [True] * 4}, resamples=100)
    assert (est.value, est.high) == (1.0, 1.0)
    assert est.low == pytest.approx(0.6756, abs=1e-3)  # Wilson 8/8, not a zero-width interval


@pytest.mark.slow
def test_bootstrap_coverage():
    rng = random.Random(7)
    cover = 0
    suites_n, n_scn, n_tr = 500, 40, 5
    true_mean = 0.5  # scenario p ~ Uniform(0, 1)
    for i in range(suites_n):
        data = {}
        for s in range(n_scn):
            p = rng.random()
            data[f"s{s}"] = [rng.random() < p for _ in range(n_tr)]
        est = suite_pass_rate(data, resamples=200, seed=i)
        cover += est.low <= true_mean <= est.high
    assert 0.92 <= cover / suites_n <= 0.98


# --- comparison ---------------------------------------------------------------------------


def test_identical_runs_no_detectable_change():
    run = {"a": [True, False, True], "b": [True] * 3, "c": [False] * 3}
    cmp = compare_runs(run, run)
    assert cmp.verdict == "no detectable change"
    assert cmp.p_value == 1.0 and cmp.delta.value == 0.0


def test_regression_and_improvement():
    a = {f"s{i}": [True] * 5 for i in range(10)}
    b = {f"s{i}": [False] * 5 for i in range(10)}
    assert compare_runs(a, b).verdict == "regression"
    assert compare_runs(b, a).verdict == "improvement"
    assert compare_runs(a, b).p_value == pytest.approx(2 / 2**10)


def test_inconclusive_message():
    a = {"s1": [True, True, False], "s2": [True, False, False], "s3": [True] * 3}
    b = {"s1": [True, False, False], "s2": [True, True, False], "s3": [True] * 3}
    cmp = compare_runs(a, b)
    assert cmp.verdict == "inconclusive"
    assert "could detect a change of about" in cmp.message and "more repetitions" in cmp.message


def test_compare_no_shared_scenarios():
    assert compare_runs({"a": [True]}, {"b": [True]}).verdict == "inconclusive"


@given(st.lists(st.floats(-1, 1, allow_nan=False), min_size=1, max_size=10), st.integers(0, 5))
def test_permutation_p_in_unit_interval_and_symmetric(diffs, seed):
    p = sign_flip_pvalue(diffs, seed=seed)
    assert 0.0 < p <= 1.0
    assert sign_flip_pvalue([-d for d in diffs], seed=seed) == pytest.approx(p)


def test_permutation_monte_carlo_branch_symmetric():
    diffs = [0.1 * ((i % 5) - 1.5) for i in range(30)]
    p = sign_flip_pvalue(diffs, seed=1)
    assert 0 < p <= 1
    assert sign_flip_pvalue([-d for d in diffs], seed=1) == p
    assert sign_flip_pvalue(diffs, seed=1) == p


def test_permutation_p_uniform_under_null():
    rng = random.Random(11)
    ps = [sign_flip_pvalue([rng.gauss(0, 1) for _ in range(12)]) for _ in range(400)]
    # P(p <= x) <= x for a valid test; check at a few points with slack.
    for x in (0.05, 0.25, 0.5):
        assert sum(p <= x for p in ps) / len(ps) <= x + 0.05


def test_fisher_known_values():
    # Classic tea-tasting table [[3,1],[1,3]]: two-sided p = 0.4857 (Fisher 1935, R fisher.test).
    assert fisher_exact(3, 4, 1, 4) == pytest.approx(0.4857, abs=1e-4)
    assert fisher_exact(5, 5, 0, 5) == pytest.approx(2 / 252)
    assert fisher_exact(2, 4, 2, 4) == pytest.approx(1.0)


def test_flip_table_categories():
    a = {"nf": [True] * 5, "np": [False] * 5, "fl": [True, False] * 3, "st": [True] * 4}
    b = {"nf": [False] * 5, "np": [True] * 5, "fl": [False, True] * 3, "st": [True] * 4}
    cats = {f.scenario_id: f.category for f in flip_table(a, b)}
    assert cats == {"nf": "newly_failing", "np": "newly_passing", "fl": "flaky", "st": "stable"}


def test_flip_single_trial_and_low_evidence():
    f = {
        x.scenario_id: x
        for x in flip_table({"a": [True], "b": [True] * 2}, {"a": [False], "b": [False] * 2})
    }
    assert f["a"].category == "newly_failing" and f["a"].note == "single trial"
    assert f["b"].category == "stable" and f["b"].note


# --- sequential ---------------------------------------------------------------------------


def test_beta_cdf_known_values():
    assert beta_cdf(0.5, 1, 1) == pytest.approx(0.5)
    assert beta_cdf(0.9, 4, 1) == pytest.approx(0.9**4)  # Beta(a,1) has cdf x**a
    assert beta_cdf(0.5, 2, 2) == pytest.approx(0.5)  # symmetric


@given(st.integers(1, 20), st.integers(1, 20), st.floats(0, 1))
def test_beta_cdf_is_a_cdf(a, b, x):
    assert -1e-12 <= beta_cdf(x, a, b) <= 1 + 1e-12
    assert beta_cdf(x, a, b) <= beta_cdf(min(1.0, x + 0.1), a, b) + 1e-12


def test_sequential_stopping():
    assert sequential_decision(2, 2, max_trials=10).decision == "continue"  # below min trials
    assert sequential_decision(30, 30, max_trials=50).decision == "stop_pass"
    assert sequential_decision(0, 6, max_trials=50).decision == "stop_fail"
    assert sequential_decision(5, 10, max_trials=10).decision == "max_reached"
    d = sequential_decision(3, 6, max_trials=50)
    assert d.posterior_mean == posterior_mean(3, 6) == 0.5


# --- agreement ----------------------------------------------------------------------------


def test_kappa_known_values():
    # Wikipedia example: 20 yes/yes, 5 yes/no, 10 no/yes, 15 no/no -> kappa = 0.4
    a = [True] * 25 + [False] * 25
    b = [True] * 20 + [False] * 5 + [True] * 10 + [False] * 15
    assert cohens_kappa(a, b) == pytest.approx(0.4)
    assert cohens_kappa([True, False], [True, False]) == 1.0
    assert cohens_kappa([True] * 3, [True] * 3) == 1.0
    assert cohens_kappa([True, False], [False, True]) == -1.0


def test_judge_agreement():
    j = [True, True, False, False, True, False, True, False]
    h = [True, False, False, False, True, True, True, False]
    ag = judge_agreement(j, h, resamples=300)
    assert ag.n == 8
    assert ag.accuracy == pytest.approx(6 / 8)
    assert ag.precision == pytest.approx(3 / 4) and ag.recall == pytest.approx(3 / 4)
    assert -1 <= ag.kappa_low <= ag.kappa <= ag.kappa_high <= 1
    assert judge_agreement([False] * 3, [False] * 3).precision is None


@given(st.lists(st.tuples(st.booleans(), st.booleans()), min_size=1, max_size=20))
def test_kappa_bounds_and_symmetry(pairs):
    a, b = [p[0] for p in pairs], [p[1] for p in pairs]
    k = cohens_kappa(a, b)
    assert -1.0 - 1e-9 <= k <= 1.0 + 1e-9
    assert k == pytest.approx(cohens_kappa(b, a))


def test_degenerate_bootstrap_falls_back_to_wilson():
    est = suite_pass_rate({"a": [False] * 2, "b": [False] * 2}, resamples=100)
    assert est.value == 0.0 and est.low == 0.0
    assert 0.45 < est.high < 0.55  # Wilson 0/4 is about 0.49
    est = suite_pass_rate({"a": [True] * 4}, resamples=100)
    assert est.high == 1.0 and 0.5 < est.low < 0.55


@given(suites)
@settings(max_examples=60, deadline=None)
def test_interval_never_zero_width_for_nonempty(data):
    est = suite_pass_rate(data, resamples=50)
    if est.n > 0:
        assert est.high > est.low
    for point in reliability_curve(data, resamples=50):
        assert point.estimate.high > point.estimate.low


# --- Beta credible interval (adaptive reports) --------------------------------------------


def test_beta_credible_interval_known_values_and_bounds():
    from gauntlet_core.stats import beta_credible_interval

    # Beta(4, 1) (3 of 3 passed): the 95% equal-tailed interval is (0.025**(1/4), 0.975**(1/4))
    lo, hi = beta_credible_interval(3, 3)
    assert (lo, hi) == pytest.approx((0.3976, 0.9937), abs=1e-3)
    for s, n in [(0, 3), (1, 4), (7, 9), (9, 9)]:
        lo, hi = beta_credible_interval(s, n)
        assert 0 <= lo < posterior_mean(s, n) < hi <= 1
    narrow, wide = beta_credible_interval(5, 8, 0.8), beta_credible_interval(5, 8, 0.99)
    assert wide[0] < narrow[0] and wide[1] > narrow[1]
