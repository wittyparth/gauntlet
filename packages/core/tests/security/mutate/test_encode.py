import pytest
from gauntlet_core.security.mutate.base import derive_id
from gauntlet_core.security.mutate.encode import (
    DECODERS,
    INSTRUCTIONS,
    EncodeMutation,
    decode_text,
    encode_text,
)
from mut_helpers import atk, issues, rng

INPUTS = ["hello world", "Say {{marker}} now", "mail {{attacker_email}} and {{canary:c1}} ok"]
EXPECTED = {
    ("base64", "hello world"): "aGVsbG8gd29ybGQ=",
    ("rot13", "hello world"): "uryyb jbeyq",
    ("hex", "hello world"): "68656c6c6f20776f726c64",
    ("url", "hello world"): "hello%20world",
    ("reverse", "hello world"): "dlrow olleh",
    ("leet", "hello world"): "h3ll0 w0rld",
    ("zerowidth", "hello world"): "hel\u200blo \u200bwor\u200bld",
    ("homoglyph", "hello world"): "hello w\u043erld",
}


@pytest.mark.parametrize(("kind", "text"), sorted(EXPECTED))
def test_fixed_outputs(kind, text):
    assert encode_text(kind, text) == f"{INSTRUCTIONS[kind]}\n{EXPECTED[(kind, text)]}"


@pytest.mark.parametrize("kind", sorted(DECODERS))
@pytest.mark.parametrize("text", INPUTS)
def test_round_trip(kind, text):
    assert decode_text(kind, encode_text(kind, text)) == text


@pytest.mark.parametrize("kind", ["base64", "rot13", "hex", "url", "reverse", "leet"])
def test_placeholders_stay_raw(kind):
    out = encode_text(kind, "go {{marker}} then {{canary:c1}}")
    assert "{{marker}}" in out and "{{canary:c1}}" in out


async def test_mutation_derives_a_valid_attack():
    [m] = await EncodeMutation("base64").apply(atk(), rng=rng(), gateway=None)
    assert m.id == derive_id("atk_demo_0001", ["encode:base64"])
    assert m.technique == "base+encode:base64"
    assert m.objective == atk().objective and m.source == "s@1:a" and m.license == "MIT"
    assert issues(m) == []


async def test_list_payload_encodes_each_turn():
    [m] = await EncodeMutation("hex").apply(atk(["one {{marker}}", "two"]), rng=rng(), gateway=None)
    assert isinstance(m.payload, list) and len(m.payload) == 2
    assert all(t.startswith(INSTRUCTIONS["hex"]) for t in m.payload)


def test_unknown_encode_rejected():
    with pytest.raises(ValueError):
        EncodeMutation("nope")
