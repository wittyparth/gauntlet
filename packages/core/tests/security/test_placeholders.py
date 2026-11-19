import pytest
from gauntlet_core.security import (
    extract_placeholders,
    is_allowed_placeholder,
    substitute,
)


def test_extract_in_order_with_repeats():
    assert extract_placeholders("a {{marker}} b {{canary:card_main}} {{ marker }}") == [
        "marker",
        "canary:card_main",
        "marker",
    ]


def test_allowed_set():
    assert is_allowed_placeholder("marker") and is_allowed_placeholder("canary:x")
    assert not is_allowed_placeholder("evil") and not is_allowed_placeholder("canary:")


def test_substitute_and_missing_key():
    assert substitute("x {{marker}} {a: 1} {{{marker}}}", {"marker": "M"}) == "x M {a: 1} {M}"
    with pytest.raises(KeyError):
        substitute("{{marker}}", {})
