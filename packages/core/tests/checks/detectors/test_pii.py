import pytest
from gauntlet_core.checks.detectors import detect_pii
from gauntlet_core.checks.detectors.pii import luhn_ok
from hypothesis import given
from hypothesis import strategies as st

POSITIVE = [
    ("write to jane.doe+tag@example.co.uk please", "email"),
    ("call me at (415) 555-2671 tomorrow", "phone"),
    ("call 415-555-2671", "phone"),
    ("international +442071838750 works", "phone"),
    ("my ssn is 123-45-6789", "ssn"),
    ("card 4242 4242 4242 4242 expires soon", "card"),
    ("card 4111-1111-1111-1111", "card"),
    ("amex 378282246310005", "card"),
    ("iban GB82 WEST 1234 5698 7654 32 thanks", "iban"),
    ("iban DE89370400440532013000", "iban"),
]
NEGATIVE = [
    "order ORD-1234567890 has shipped",
    "order #4155552671 is delayed",
    "card 4242 4242 4242 4241 failed",
    "ssn 000-12-3456 and 666-12-3456 and 900-12-3456 and 123-00-4567 and 123-45-0000",
    "timestamp 1700000000 and version 3.11.4",
    "iban GB82 WEST 1234 5698 7654 33 wrong checksum",
    "the word token appears here, and a@b is not an email",
    "price 1,234,567.89 USD",
    "2024-01-15 12:30:45",
]


@pytest.mark.parametrize(("text", "kind"), POSITIVE)
def test_positive(text, kind):
    assert kind in {h.label for h in detect_pii(text)}, text


@pytest.mark.parametrize("text", NEGATIVE)
def test_negative(text):
    assert detect_pii(text) == [], text


def test_allow_list_and_kinds():
    assert detect_pii("me@example.com", allow=["me@example.com"]) == []
    assert detect_pii("me@example.com 123-45-6789", kinds=["ssn"])[0].label == "ssn"
    with pytest.raises(ValueError):
        detect_pii("x", kinds=["bogus"])


def test_hit_quote_and_span():
    h = detect_pii("x 123-45-6789 y")[0]
    assert (h.quote, h.start, h.end) == ("123-45-6789", 2, 13)


def luhn_number(body: list[int]) -> str:
    for check in range(10):
        s = "".join(map(str, [*body, check]))
        if luhn_ok(s):
            return s
    raise AssertionError


@given(st.lists(st.integers(0, 9), min_size=15, max_size=15))
def test_luhn_valid_16_digit_always_detected(body):
    n = luhn_number(body)
    assert any(h.label == "card" for h in detect_pii(f"pay with {n} now", kinds=["card"]))


@given(st.lists(st.integers(0, 9), min_size=15, max_size=15), st.integers(1, 9))
def test_luhn_broken_never_detected(body, delta):
    n = luhn_number(body)
    broken = n[:-1] + str((int(n[-1]) + delta) % 10)
    assert detect_pii(broken, kinds=["card"]) == []
