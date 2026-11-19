import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pytest
from check_helpers import chk
from gauntlet_core.checks import match_value, resolve_path
from gauntlet_core.schema import Matcher
from hypothesis import given
from hypothesis import strategies as st


def m(**kw):
    return Matcher.model_validate(kw)


def test_resolve_path():
    obj = {"a": {"b": 1}, "items": [{"sku": "x", "q": 1}, {"sku": "y"}], "l": [10, 20]}
    assert resolve_path(obj, "a.b") == [1]
    assert resolve_path(obj, "items[*].sku") == ["x", "y"]
    assert resolve_path(obj, "items[1].sku") == ["y"]
    assert resolve_path(obj, "items[*].q") == [1]
    assert resolve_path(obj, "l[*]") == [10, 20]
    assert resolve_path(obj, "nope.x") == []
    assert resolve_path(obj, "") == [obj]
    assert resolve_path(obj, "l[5]") == []
    assert resolve_path({"a": None}, "a") == [None]


@pytest.mark.parametrize(
    "matcher,value,expected",
    [
        (m(eq=3), 3, True),
        (m(eq=3), 4, False),
        (m(eq=None), None, True),
        (m(ne=3), 4, True),
        (m(ne=3), 3, False),
        (m(**{"in": [1, 2]}), 2, True),
        (m(**{"in": [1, 2]}), 3, False),
        (m(regex=r"^ab+c$"), "abbc", True),
        (m(regex=r"^ab+c$"), "xabc", False),
        (m(regex="a"), 5, False),
        (m(contains="ell"), "hello", True),
        (m(contains="x"), "hello", False),
        (m(contains=2), [1, 2], True),
        (m(contains="k"), {"k": 1}, True),
        (m(gt=1), 2, True),
        (m(gt=1), 1, False),
        (m(gte=1), 1, True),
        (m(lt=1), 0.5, True),
        (m(lte=1), 1.5, False),
        (m(gt=1), "5", False),
        (m(gt=0), True, False),
        (m(exists=True), 0, True),
        (m(exists=True), None, True),
        (m(gte=1, lte=3), 2, True),
        (m(gte=1, lte=3), 4, False),
    ],
)
def test_match_value(matcher, value, expected):
    assert match_value(matcher, value) is expected


def test_missing_values():
    assert match_value(m(exists=False), None, present=False)
    assert not match_value(m(exists=True), None, present=False)
    assert match_value(m(ne=1), None, present=False)
    assert not match_value(m(eq=1), None, present=False)
    assert not match_value(m(gt=0), None, present=False)


def test_ref_ops():
    assert match_value(m(ref="args:x"), 5, ref_value=5)
    assert not match_value(m(ref="args:x"), 5, ref_value=6)
    assert match_value(m(ref="args:x", ref_op="lte"), 5, ref_value=6)
    assert not match_value(m(ref="args:x", ref_op="gt"), 5, ref_value=6)
    assert match_value(m(ref="args:x", ref_op="ne"), 5, ref_value=6)
    assert not match_value(m(ref="args:x", ref_op="lt"), "a", ref_value=6)


def test_unresolved_ref_never_matches():
    assert not match_value(m(ref="args:x", ref_op="ne"), 5)


def test_bad_regex_does_not_match_or_raise():
    assert not match_value(m(regex="("), "x")


def test_regex_pattern_too_long_is_rejected():
    assert not match_value(m(regex="a" * 5000), "a" * 5000)


@given(st.integers(-100, 100), st.integers(-100, 100))
def test_comparison_operators_agree_with_python(v, t):
    assert match_value(m(gt=t), v) == (v > t)
    assert match_value(m(gte=t), v) == (v >= t)
    assert match_value(m(lt=t), v) == (v < t)
    assert match_value(m(lte=t), v) == (v <= t)
    assert match_value(m(eq=t), v) == (v == t)
    assert match_value(m(ne=t), v) == (v != t)


@given(st.text(max_size=20), st.text(max_size=5))
def test_contains_matches_python_in(s, sub):
    assert match_value(m(contains=sub), s) == (sub in s)


def test_check_yaml_shape_validates():
    c = chk({"type": "tool_called", "tool": "refund", "args": {"amount": {"gt": 10}}})
    assert c.args["amount"].gt == 10
