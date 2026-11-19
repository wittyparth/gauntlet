from gauntlet_core.targets import MISSING, get_path, set_path
from hypothesis import given
from hypothesis import strategies as st


def test_get_nested_and_index():
    doc = {"a": {"b": [{"c": 5}, {"c": 6}]}, "x": None}
    assert get_path(doc, "a.b[1].c") == 6
    assert get_path(doc, "x") is None  # present None is not missing


def test_missing_is_sentinel_not_none():
    doc = {"a": [1]}
    for p in ("b", "a[3]", "a.b", "a[0].z"):
        assert get_path(doc, p) is MISSING
    assert not MISSING


def test_set_creates_containers():
    doc: dict = {}
    set_path(doc, "a.b[1].c", 9)
    assert doc == {"a": {"b": [None, {"c": 9}]}}
    set_path(doc, "a.b[0]", "x")
    assert get_path(doc, "a.b[0]") == "x"


@given(
    st.lists(st.text("abcd", min_size=1, max_size=3), min_size=1, max_size=4),
    st.integers(),
)
def test_set_then_get_roundtrip(keys, value):
    doc: dict = {}
    path = ".".join(keys)
    set_path(doc, path, value)
    assert get_path(doc, path) == value
