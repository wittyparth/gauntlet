from gauntlet_core.eval.cluster import ClusterName, Exemplar, MemoryNameCache, name_cluster
from gauntlet_core.llm import FakeLLM, FakeReply

EX = [Exemplar("ep_1", "refund issued without asking"), Exemplar("ep_2", "refund again")]
NAMED = {
    "name": "Unconfirmed refunds in checkout flows today",
    "description": "The agent issues refunds without asking the user first.",
    "suspected_cause": "The prompt never requires confirmation.",
}


async def test_structured_name_from_the_generator_role():
    llm = FakeLLM(by_role={"generator": [FakeReply(parsed=NAMED)]})
    out = await name_cluster(EX, llm, fallback="Cluster 0: x")
    assert isinstance(out, ClusterName) and out.name.startswith("Unconfirmed refunds")
    assert [c.role for c in llm.calls] == ["generator"]
    prompt = llm.calls[0].messages[-1]["content"]
    assert "refund issued without asking" in prompt


async def test_name_is_cut_to_six_words_and_description_to_thirty():
    long = {**NAMED, "name": "one two three four five six seven eight",
            "description": " ".join(["w"] * 45)}  # fmt: skip
    llm = FakeLLM(by_role={"generator": [FakeReply(parsed={**long, "name": long["name"]})]})
    out = await name_cluster(EX, llm, fallback="f")
    assert out.name == "one two three four five six" and len(out.description.split()) == 30


async def test_cache_hit_makes_no_call_and_key_ignores_member_order():
    cache = MemoryNameCache()
    llm = FakeLLM(by_role={"generator": [FakeReply(parsed=NAMED)]})
    first = await name_cluster(EX, llm, fallback="f", member_ids=["a", "b"], cache=cache)
    second = await name_cluster(EX, llm, fallback="f", member_ids=["b", "a"], cache=cache)
    assert first == second and len(llm.calls) == 1
    other = FakeLLM(by_role={"generator": [FakeReply(parsed=NAMED)]})
    await name_cluster(EX, other, fallback="f", member_ids=["a", "b"], model="m2", cache=cache)
    assert len(other.calls) == 1  # another model is another key


async def test_failure_to_name_falls_back_and_is_not_cached():
    cache = MemoryNameCache()
    llm = FakeLLM(by_role={"generator": []})  # exhausted: raises
    out = await name_cluster(
        EX, llm, fallback="Cluster 2: no_refund", member_ids=["a"], cache=cache
    )
    assert out.name == "Cluster 2: no_refund" and out.description == ""
    ok = FakeLLM(by_role={"generator": [FakeReply(parsed=NAMED)]})
    again = await name_cluster(EX, ok, fallback="x", member_ids=["a"], cache=cache)
    assert again.name != "x" and len(ok.calls) == 1
