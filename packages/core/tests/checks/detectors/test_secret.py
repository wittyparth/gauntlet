import string

import pytest
from gauntlet_core.checks.detectors import detect_secret
from hypothesis import given, settings
from hypothesis import strategies as st

POSITIVE = [
    ("aws AKIAIOSFODNN7EXAMPLE here", "aws_key"),
    ("gh ghp_" + "a1B2c3D4e5" * 4, "github_token"),
    ("slack xoxb-1234567890-abcdefghij", "slack_token"),
    ("stripe sk_live_" + "4eC39HqLyjWDarjtT1zdp7dc", "stripe_key"),
    ("anthropic sk-ant-api03-abcdefghijklmnop12345", "api_key"),
    ("openai sk-proj-abcdefghijklmnopqrstu", "api_key"),
    ("google AIza" + "Sy" + "A" * 33, "google_key"),
    ("jwt eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.SflKxwRJSMeKKF2QT4", "jwt"),
    ("-----BEGIN RSA PRIVATE KEY-----", "private_key"),
    ("config password = 'Zx9Qw3rTy7UiOp2Kd'", None),
    ("API_KEY: q8Xz2LmN5vB7cR1tY4uW", "generic_secret"),
]
NEGATIVE = [
    "please send the token to the user",
    "the password must be at least 16 characters long",
    "password: aaaaaaaaaaaaaaaaaaaa",
    "token = 1111111111111111",
    "sk-short",
    "AKIA is a prefix",
    "secret: abababababababababab",
    "ghp_ is how github tokens start",
]


@pytest.mark.parametrize(("text", "label"), POSITIVE)
def test_positive(text, label):
    hits = detect_secret(text)
    assert hits, text
    if label:
        assert label in {h.label for h in hits}


@pytest.mark.parametrize("text", NEGATIVE)
def test_negative(text):
    assert detect_secret(text) == [], text


def test_anthropic_key_not_double_counted():
    assert len(detect_secret("sk-ant-api03-abcdefghijklmnop12345")) == 1


def test_quote_truncated():
    key = "sk-" + "a" * 200
    assert len(detect_secret(key)[0].quote) == 80


@settings(max_examples=10_000, deadline=None)
@given(st.text(alphabet=string.printable, min_size=5, max_size=200))
def test_random_strings_never_fire(s):
    assert detect_secret(s) == []
