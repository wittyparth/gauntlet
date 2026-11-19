import pytest
from gauntlet_core.eval import SEVERITY_WEIGHT, composite_score, dimension_score
from gauntlet_core.eval.scoring import hard_fail_episodes
from gauntlet_core.schema import Verdict
from hypothesis import given
from hypothesis import strategies as st


def test_known_dimension_scores():
    assert dimension_score(3, 1) == 0.75
    assert dimension_score(0, 0) is None
    assert dimension_score(0, 4) == 0.0


def test_weights():
    assert SEVERITY_WEIGHT == {"low": 1, "medium": 2, "high": 4, "critical": 8}


def test_composite_known_value_and_none_skipped():
    dims = [(1.0, "high"), (0.5, "low"), (None, "critical"), (0.0, "medium")]
    # (4*1 + 1*0.5 + 2*0) / (4 + 1 + 2)
    assert composite_score(dims) == pytest.approx(4.5 / 7)
    assert composite_score([(None, "high")]) is None
    assert composite_score([]) is None


def test_hard_fail_episodes_lists_only_failing_hard_fail():
    def v(result, hard):
        return Verdict(evaluator="e", criterion="c", result=result, hard_fail=hard)

    got = hard_fail_episodes(
        {"b": [v("fail", True)], "a": [v("fail", True)], "c": [v("fail", False), v("pass", True)]}
    )
    assert got == ["a", "b"]


@given(st.integers(0, 50), st.integers(0, 50))
def test_score_in_unit_interval(p, f):
    s = dimension_score(p, f)
    assert s is None or 0.0 <= s <= 1.0


@given(
    st.lists(
        st.tuples(st.one_of(st.none(), st.floats(0, 1)), st.sampled_from(list(SEVERITY_WEIGHT))),
        max_size=8,
    )
)
def test_composite_between_min_and_max(dims):
    c = composite_score(dims)
    present = [s for s, _ in dims if s is not None]
    if not present:
        assert c is None
    else:
        assert min(present) - 1e-9 <= (c or 0) <= max(present) + 1e-9
