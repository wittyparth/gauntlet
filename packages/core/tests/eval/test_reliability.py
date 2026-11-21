import itertools
import math

import pytest
from gauntlet_core.eval.reliability import reliability_curve
from gauntlet_core.stats import pass_hat_k, suite_pass_rate
from hypothesis import given, settings
from hypothesis import strategies as st


@pytest.mark.parametrize("c", range(6))
def test_pass_hat_k_known_values_n5(c):
    for k in range(1, 6):
        assert pass_hat_k(c, 5, k) == pytest.approx(math.comb(c, k) / math.comb(5, k))


def data_n5():
    return {
        "a": [True] * 5,
        "b": [True, True, True, False, False],
        "c": [False] * 5,
        "d": [True, False, True, True, True],
    }


def test_curve_points_have_intervals_and_counts():
    pts = reliability_curve(data_n5(), seed=1)
    assert [p.k for p in pts] == [1, 2, 3, 4, 5]
    assert all(p.scenarios == 4 and p.ci_low <= p.value <= p.ci_high for p in pts)
    # known value at k=2: mean of C(c,2)/C(5,2) over c = 5, 3, 0, 4
    assert pts[1].value == pytest.approx((1 + 0.3 + 0 + 0.6) / 4)


def test_pass_one_equals_the_suite_pass_rate():
    d = data_n5()
    got = reliability_curve(d, seed=1)[0].value
    assert got == pytest.approx(suite_pass_rate(d, seed=1).value, abs=1e-9)


@settings(max_examples=40, deadline=None)
@given(
    st.dictionaries(
        st.text("abc", min_size=1, max_size=2),
        st.lists(st.booleans(), min_size=1, max_size=7),
        min_size=1,
        max_size=5,
    )
)
def test_curve_is_non_increasing_when_every_scenario_has_all_k(d):
    n = min(len(v) for v in d.values())
    same = {k: v[:n] for k, v in d.items()}
    pts = reliability_curve(same, seed=0, resamples=50)
    assert pts[0].value == pytest.approx(suite_pass_rate(same, seed=0, resamples=50).value)
    values = [p.value for p in pts]
    assert all(a >= b - 1e-12 for a, b in itertools.pairwise(values))


def test_scenarios_with_fewer_trials_than_k_are_excluded_and_counted():
    d = {"a": [True, True, False, True], "b": [True, False], "c": [True]}
    pts = reliability_curve(d, seed=0)
    assert [(p.k, p.scenarios) for p in pts] == [(1, 3), (2, 2), (3, 1), (4, 1)]


def test_k_max_and_single_trial_curve():
    d = {"a": [True] * 10, "b": [False] * 10}
    assert [p.k for p in reliability_curve(d, seed=0)] == list(range(1, 9))
    assert [p.k for p in reliability_curve(d, seed=0, k_max=3)] == [1, 2, 3]
    one = reliability_curve({"a": [True], "b": [False]}, seed=0)
    assert [p.k for p in one] == [1]
    assert reliability_curve({}, seed=0) == []
