from __future__ import annotations

import httpx
import pytest
import respx
from gauntlet_core.engine import EpisodeCtx, MemoryJournalStore, TargetError
from gauntlet_core.schema import OpenAICompatTargetConfig
from gauntlet_core.targets import OpenAICompatTarget, UrlPolicy
from helpers import make_ctx

POLICY = UrlPolicy(allow_private=True)


async def nosleep(_: float) -> None:
    return None


def target(base_url: str, client: httpx.AsyncClient, **kw) -> OpenAICompatTarget:
    cfg = OpenAICompatTargetConfig(base_url=base_url, model="m", api_key_secret=kw.pop("key", None))
    return OpenAICompatTarget(
        cfg, secrets=kw.pop("secrets", {}), client=client, safety=POLICY, sleep=nosleep, **kw
    )


async def test_reply_extracted_and_history_sent(fake):
    async with httpx.AsyncClient() as c:
        t = target(fake.base_url + "/v1", c)
        ctx = await make_ctx()
        await t.open(ctx)
        assert await t.send(ctx, "hello") == "echo: hello"
        assert await t.send(ctx, "again") == "echo: again"
    body = fake.requests[1]["body"]
    assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user"]
    assert body["temperature"] == 0 and body["model"] == "m"


async def test_bearer_secret(fake):
    async with httpx.AsyncClient() as c:
        t = target(fake.base_url + "/v1", c, key="K", secrets={"K": "sk-123"})
        ctx = await make_ctx()
        await t.open(ctx)
        await t.send(ctx, "x")
    assert fake.requests[0]["headers"]["authorization"] == "Bearer sk-123"


async def test_retry_503_twice_then_ok(fake):
    fake.failures = [503, 503]
    async with httpx.AsyncClient() as c:
        t = target(fake.base_url + "/v1", c)
        ctx = await make_ctx()
        await t.open(ctx)
        assert await t.send(ctx, "x") == "echo: x"
    assert len(fake.requests) == 3


async def test_400_fails_fast(fake):
    fake.failures = [400]
    async with httpx.AsyncClient() as c:
        t = target(fake.base_url + "/v1", c)
        ctx = await make_ctx()
        await t.open(ctx)
        with pytest.raises(TargetError) as e:
            await t.send(ctx, "x")
    assert e.value.code == "http_400" and len(fake.requests) == 1


async def test_persistent_500_is_unreachable(fake):
    fake.failures = [500] * 10
    async with httpx.AsyncClient() as c:
        t = target(fake.base_url + "/v1", c)
        ctx = await make_ctx()
        await t.open(ctx)
        with pytest.raises(TargetError) as e:
            await t.send(ctx, "x")
    assert e.value.code == "unreachable" and len(fake.requests) == 4


@respx.mock
async def test_bad_reply_shape_and_connect_error():
    route = respx.post("http://agent.test/chat/completions")
    route.mock(return_value=httpx.Response(200, json={"choices": [{"message": {"content": None}}]}))
    async with httpx.AsyncClient() as c:
        t = target("http://agent.test", c)
        ctx = await make_ctx()
        await t.open(ctx)
        with pytest.raises(TargetError) as e:
            await t.send(ctx, "x")
    assert e.value.code == "bad_reply"
    route.mock(side_effect=httpx.ConnectError("no"))
    async with httpx.AsyncClient() as c:
        t = target("http://agent.test", c)
        ctx = await make_ctx()
        await t.open(ctx)
        with pytest.raises(TargetError) as e2:
            await t.send(ctx, "x")
    assert e2.value.code == "unreachable"


async def test_blocked_url_and_missing_secret():
    async with httpx.AsyncClient() as c:
        cfg = OpenAICompatTargetConfig(base_url="http://169.254.169.254", model="m")
        t = OpenAICompatTarget(cfg, secrets={}, client=c, safety=UrlPolicy(), sleep=nosleep)
        ctx = await make_ctx()
        await t.open(ctx)
        with pytest.raises(TargetError) as e:
            await t.send(ctx, "x")
        assert e.value.code == "blocked_url"
        t2 = target("http://agent.test", c, key="NOPE")
        with pytest.raises(TargetError) as e2:
            await t2.send(ctx, "x")
        assert e2.value.code == "missing_secret"


async def test_replay_makes_no_second_request(fake):
    store = MemoryJournalStore()
    async with httpx.AsyncClient() as c:
        ctx = await make_ctx(store)
        t = target(fake.base_url + "/v1", c)
        await t.open(ctx)
        await t.send(ctx, "hi")
        store.bump_epoch("ep")
        ctx2 = await EpisodeCtx.open(store, "ep", run_id="r", rng_seed=7)
        t2 = target(fake.base_url + "/v1", c)
        await t2.open(ctx2)
        assert await t2.send(ctx2, "hi") == "echo: hi"
    assert len(fake.requests) == 1
