import random

from gauntlet_core.sim import apply_typos
from hypothesis import given
from hypothesis import strategies as st

words = st.text("abcdefghij", min_size=1, max_size=9)
tokens = st.one_of(
    words,
    st.from_regex(r"[a-z]{2,5}[0-9]{2,4}", fullmatch=True),
    st.from_regex(r"[a-z]+@[a-z]+\.com", fullmatch=True),
    st.just("#4411"),
)
texts = st.lists(tokens, min_size=1, max_size=10).map(" ".join)


def rng_of(seed: int):
    r = random.Random(seed)
    return r.random


@given(texts, st.integers(0, 10_000))
def test_ids_and_emails_untouched_and_length_bounded(text, seed):
    out = apply_typos(text, 1.0, rng_of(seed))
    src, dst = text.split(" "), out.split(" ")
    assert len(src) == len(dst)
    for a, b in zip(src, dst, strict=True):
        if any(c.isdigit() for c in a) or "@" in a or "#" in a or len(a) < 4:
            assert a == b
        else:
            assert abs(len(a) - len(b)) <= 1


@given(texts, st.integers(0, 100))
def test_rate_zero_is_identity(text, seed):
    assert apply_typos(text, 0.0, rng_of(seed)) == text


@given(texts, st.integers(0, 10_000), st.floats(0, 1))
def test_same_stream_same_output(text, seed, rate):
    assert apply_typos(text, rate, rng_of(seed)) == apply_typos(text, rate, rng_of(seed))


def test_changes_something_at_full_rate():
    assert apply_typos("please refund my order quickly", 1.0, rng_of(3)) != (
        "please refund my order quickly"
    )
