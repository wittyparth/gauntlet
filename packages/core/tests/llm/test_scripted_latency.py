import time

from gauntlet_core.llm.scripted import ScriptedLLM


async def test_latency_s_delays_every_reply():
    llm = ScriptedLLM({"latency_s": 0.05, "roles": {"r": ["hi"]}})
    t0 = time.perf_counter()
    res = await llm.complete("r", [{"role": "user", "content": "x"}])
    assert res.text == "hi"
    assert time.perf_counter() - t0 >= 0.05
