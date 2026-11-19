from gauntlet_core.security.mutate.base import derive_id
from gauntlet_core.security.mutate.split import SUFFIX, SplitMutation, split_parts
from mut_helpers import atk, issues, rng


def test_sentence_split_and_atomic_placeholders():
    parts = split_parts("First one. Use {{canary:a.b}} here. Third part. Fourth bit.", 2)
    assert parts is not None and len(parts) == 2
    assert "".join(parts).count("{{canary:a.b}}") == 1
    assert any("{{canary:a.b}}" in p for p in parts)  # never cut inside


def test_single_sentence_yields_none():
    assert split_parts("just one sentence with {{marker}}", 3) is None


def test_fewer_sentences_than_parts_splits_at_whitespace():
    parts = split_parts("Alpha beta gamma delta. Epsilon zeta eta theta.", 4)
    assert parts is not None and len(parts) == 4


async def test_suffix_format_requires_and_validity():
    a = atk("One sentence here. Two is here {{marker}}. Three is here.")
    [m] = await SplitMutation(3).apply(a, rng=rng(), gateway=None)
    assert isinstance(m.payload, list) and len(m.payload) == 3
    assert m.payload[0].endswith(SUFFIX.format(i=1, n=3))
    assert m.payload[1].endswith(SUFFIX.format(i=2, n=3))
    assert "more follows" not in m.payload[2]
    assert "multi_turn" in m.requires and m.id == derive_id("atk_demo_0001", ["split:3"])
    assert issues(m) == []


async def test_single_sentence_attack_skipped():
    assert await SplitMutation(2).apply(atk("only one {{marker}}"), rng=rng(), gateway=None) == []
