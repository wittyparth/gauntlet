import asyncio

from gauntlet_core.schema import Attack
from gauntlet_core.security import extract_placeholders
from gauntlet_core.security.mutate import apply_mutations
from hypothesis import given, settings
from hypothesis import strategies as st
from mut_helpers import atk, issues

PH = ["{{marker}}", "{{attacker_email}}", "{{attacker_url}}", "{{canary:c1}}", "{{honeytool}}"]
WORDS = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789 ,", min_size=1, max_size=30)
SENT = st.builds(lambda w, p: f"{w} {p}.", WORDS, st.sampled_from(PH) | st.just(""))
PAYLOADS = st.lists(SENT, min_size=1, max_size=5).map(" ".join)
SPECS = [
    "encode:base64", "encode:rot13", "encode:hex", "encode:url", "encode:reverse", "encode:leet",
    "encode:homoglyph", "encode:zerowidth", "wrap:fiction", "wrap:roleplay", "split:2",
    "split:3", "split:4", "embed:body", "embed:footer", "embed:html_comment",
    "embed:hidden_text", "embed:metadata",
]  # fmt: skip


def run(a: Attack, seed: int = 0) -> list[Attack]:
    return asyncio.run(apply_mutations([a], SPECS, seed=seed, max_variants_per_attack=len(SPECS)))


def bag(p: str | list[str]) -> list[str]:
    return sorted(x for t in ([p] if isinstance(p, str) else p) for x in extract_placeholders(t))


@settings(max_examples=60, deadline=None)
@given(PAYLOADS)
def test_placeholder_multiset_is_invariant(payload):
    a = atk(payload.strip() or "x")
    for m in run(a):
        assert bag(m.payload) == bag(a.payload), m.id


@settings(max_examples=30, deadline=None)
@given(PAYLOADS, st.integers(0, 5))
def test_deterministic_for_equal_seeds(payload, seed):
    a = atk(payload)
    assert run(a, seed) == run(a, seed)


@settings(max_examples=40, deadline=None)
@given(PAYLOADS)
def test_outputs_validate(payload):
    a = atk(payload)
    for m in run(a):
        assert issues(m) == [], m.id
        assert m.objective == a.objective and m.severity == a.severity
