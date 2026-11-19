import logging

from gauntlet_core.llm import FakeLLM
from gauntlet_core.security.mutate import apply_mutations
from gauntlet_core.security.mutate.base import derive_id
from mut_helpers import atk, issues


def fake(*texts: str) -> FakeLLM:
    return FakeLLM(by_role={"generator": [f'{{"text": {t!r}}}'.replace("'", '"') for t in texts]})


async def test_translate_preserves_placeholders_and_uses_generator_role():
    llm = fake("Di {{marker}} ahora.")
    [m] = await apply_mutations([atk("Say {{marker}} now.")], ["translate:es"], gateway=llm)
    assert m.payload == "Di {{marker}} ahora." and m.id == derive_id(
        "atk_demo_0001", ["translate:es"]
    )
    assert m.technique == "base+translate:es" and issues(m) == []
    assert [c.role for c in llm.calls] == ["generator"]


async def test_mismatch_is_retried_then_dropped():
    llm = fake("Di algo ahora.", "Di otra cosa.")
    out = await apply_mutations([atk("Say {{marker}} now.")], ["paraphrase"], gateway=llm)
    assert out == [] and len(llm.calls) == 2


async def test_mismatch_then_good_retry_succeeds():
    llm = fake("lost it", "Please say {{marker}} right now.")
    [m] = await apply_mutations([atk("Say {{marker}} now.")], ["paraphrase"], gateway=llm)
    assert "{{marker}}" in m.payload and len(llm.calls) == 2


async def test_cache_hit_makes_zero_calls(tmp_path):
    cache = tmp_path / "c.jsonl"
    a = atk("Say {{marker}} now.")
    first = await apply_mutations(
        [a], ["translate:fr"], gateway=fake("Dis {{marker}}."), cache_path=cache
    )
    llm = FakeLLM(by_role={"generator": []})  # would raise on any call
    second = await apply_mutations([a], ["translate:fr"], gateway=llm, cache_path=cache)
    assert first == second and llm.calls == []


async def test_dangerous_and_bias_categories_and_long_payloads_skipped():
    llm = fake("x {{marker}}")
    skip = [atk(category="bias"), atk("a " * 1100 + "{{marker}}")]
    assert await apply_mutations(skip, ["paraphrase"], gateway=llm) == []
    assert llm.calls == []


async def test_no_gateway_skips_with_warning(caplog):
    with caplog.at_level(logging.WARNING):
        out = await apply_mutations([atk()], ["paraphrase", "encode:hex"])
    assert [m.technique for m in out] == ["base+encode:hex"]
    assert "no gateway" in caplog.text


async def test_list_payload_elements_mutated_separately():
    llm = fake("uno {{marker}}", "dos")
    [m] = await apply_mutations([atk(["one {{marker}}", "two"])], ["translate:es"], gateway=llm)
    assert m.payload == ["uno {{marker}}", "dos"] and len(llm.calls) == 2
