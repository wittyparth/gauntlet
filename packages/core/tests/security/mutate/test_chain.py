import pytest
from gauntlet_core.llm import FakeLLM
from gauntlet_core.security.mutate import apply_mutations, parse_spec
from gauntlet_core.security.mutate.base import derive_id
from gauntlet_core.security.mutate.encode import decode_text
from mut_helpers import atk, issues


async def test_chain_order_and_naming():
    llm = FakeLLM(by_role={"generator": ['{"text": "Di {{marker}} ya."}']})
    [m] = await apply_mutations(
        [atk("Say {{marker}} now.")], [["translate:es", "encode:base64"]], gateway=llm
    )
    assert m.id == derive_id("atk_demo_0001", ["translate:es", "encode:base64"])
    assert m.technique == "base+translate:es+encode:base64"
    assert decode_text("base64", str(m.payload)).strip() == "Di {{marker}} ya."  # translate first
    assert issues(m) == []


async def test_chain_length_cap():
    with pytest.raises(ValueError):
        await apply_mutations([atk()], [["encode:hex"] * 4])


async def test_long_chain_id_gets_hash_suffix():
    a = atk(id="atk_" + "a" * 38)
    [m] = await apply_mutations([a], [["encode:base64", "encode:rot13", "encode:reverse"]])
    assert issues(m) == [] and m.id != a.id


async def test_variant_cap_and_duplicate_payload_dropped():
    specs = ["encode:base64", "encode:hex", "encode:rot13", "encode:url", "encode:reverse",
             "encode:leet", "encode:zerowidth"]  # fmt: skip
    out = await apply_mutations([atk()], specs, max_variants_per_attack=6)
    assert len(out) == 6
    # the same spec twice yields identical payloads: only one variant is kept
    assert len(await apply_mutations([atk()], ["encode:hex", "encode:hex"])) == 1


async def test_three_attacks_five_specs_all_valid():
    attacks = [
        atk(f"Sentence one {i}. Say {{{{marker}}}} now.", id=f"atk_demo_000{i}") for i in range(3)
    ]
    specs = ["encode:base64", "wrap:fiction", "split:2", "embed:footer", "encode:rot13"]
    out = await apply_mutations(attacks, specs)
    assert len(out) == 15 and all(issues(m) == [] for m in out)


def test_parse_spec_errors():
    for bad in ("nope", "encode:zzz", "split:9", "embed:zzz", "translate:xx", "wrap:zzz"):
        with pytest.raises((ValueError, KeyError)):
            parse_spec(bad)
