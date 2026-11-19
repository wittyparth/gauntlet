import math

from gauntlet_core.llm import FakeLLM, GatewayConfig, HashEmbedder, LocalRateLimiter, cosine
from gauntlet_core.llm.pricing import cost_from_pricing, estimate_micros


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    async def sleep(self, s):
        self.t += s


async def test_third_acquire_at_rpm2_waits_30s():
    c = Clock()
    lim = LocalRateLimiter(2, 10**9, clock=c, sleep=c.sleep)
    await lim.acquire("p", 1)
    await lim.acquire("p", 1)
    assert c.t == 0
    await lim.acquire("p", 1)
    assert 29.9 <= c.t <= 30.1


async def test_token_bucket_respected():
    c = Clock()
    lim = LocalRateLimiter(1000, 600, clock=c, sleep=c.sleep)
    await lim.acquire("p", 600)
    await lim.acquire("p", 300)
    assert 29.9 <= c.t <= 30.1


def test_known_prices_exact():
    p = GatewayConfig().llm.pricing
    q = p["openrouter/qwen/qwen3.7-flash"]
    g = p["openrouter/google/gemini-2.5-flash-lite"]
    d = p["openrouter/deepseek/deepseek-v4-flash"]
    assert cost_from_pricing(q, 1_000_000, 1_000_000) == 160_000
    assert cost_from_pricing(g, 1_000_000, 1_000_000) == 500_000
    assert cost_from_pricing(d, 1_000_000, 1_000_000) == 270_000
    assert cost_from_pricing(q, 1000, 100) == 43


def test_estimate_at_least_actual():
    p = GatewayConfig().llm.pricing
    m = "openrouter/qwen/qwen3.7-flash"
    assert estimate_micros(p, m, 1000, 500) >= cost_from_pricing(p[m], 1000, 300)
    assert estimate_micros({}, "x/y", 10, 10) == 0


def test_embed_deterministic_unit_norm_and_similarity():
    e = HashEmbedder()
    a = e.embed_one("please refund my order")
    assert a == e.embed_one("please refund my order")
    assert math.isclose(math.sqrt(sum(x * x for x in a)), 1.0)
    assert cosine(a, e.embed_one("refund the order please")) > cosine(
        a, e.embed_one("weather in paris tomorrow")
    )


async def test_fake_embed():
    assert len(await FakeLLM().embed("embedder", ["a", "b"])) == 2
