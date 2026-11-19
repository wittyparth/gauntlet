from __future__ import annotations

import httpx
import pytest
from gauntlet_core.engine import EpisodeCtx, IndeterminateEffect, MemoryJournalStore, TargetError
from gauntlet_core.schema import HttpTargetConfig
from gauntlet_core.targets import HttpTarget, UrlPolicy, render_template
from helpers import make_ctx

POLICY = UrlPolicy(allow_private=True)


async def nosleep(_: float) -> None:
    return None


def cfg(url: str, **kw) -> HttpTargetConfig:
    base = {
        "url": url,
        "headers": {},
        "body_template": {"text": "{{message}}", "conversation_id": "{{conversation_id}}"},
        "reply_path": "data.answer",
        "conversation_id_path": "data.cid",
        "stateful": False,
    }
    return HttpTargetConfig.model_validate({**base, **kw})


def make(c: HttpTargetConfig, client: httpx.AsyncClient, secrets=None) -> HttpTarget:
    return HttpTarget(c, secrets=secrets or {}, client=client, safety=POLICY, sleep=nosleep)


def test_template_raw_vs_inline():
    vals = {"message": "hi", "history": [{"role": "user", "content": "a"}], "conversation_id": "c1"}
    out = render_template(
        {"h": "{{history}}", "s": "say {{message}} in {{conversation_id}}", "n": 3}, vals
    )
    assert out == {"h": vals["history"], "s": "say hi in c1", "n": 3}


async def test_reply_extracted_stateless(fake):
    async with httpx.AsyncClient() as c:
        t = make(cfg(fake.base_url + "/agent"), c)
        ctx = await make_ctx()
        await t.open(ctx)
        assert await t.send(ctx, "yo") == "got: yo"
    assert fake.requests[0]["body"] == {"text": "yo", "conversation_id": ""}
    assert t.stateful is False


async def test_stateful_conversation_id_replay_and_pending_not_retry_safe(fake):
    store = MemoryJournalStore()
    conf = cfg(fake.base_url + "/agent?ids=1", stateful=True)
    async with httpx.AsyncClient() as c:
        t = make(conf, c)
        assert t.stateful is True
        ctx = await make_ctx(store)
        await t.open(ctx)
        await t.send(ctx, "one")
        await t.send(ctx, "two")
        assert fake.requests[1]["body"]["conversation_id"] == "conv_1"
        # replay restores the conversation id from the recorded result, no new requests
        store.bump_epoch("ep")
        ctx2 = await EpisodeCtx.open(store, "ep", run_id="r", rng_seed=7)
        t2 = make(conf, c)
        await t2.open(ctx2)
        await t2.send(ctx2, "one")
        await t2.send(ctx2, "two")
        assert t2.conversation_id == "conv_1" and len(fake.requests) == 2
        await t2.send(ctx2, "three")
    # a pending stateful effect cannot be retried
    effects = (await store.load("ep")).effects
    pending = effects["target:2"].model_copy(update={"status": "pending", "result": None})
    store.bump_epoch("ep")
    store._journals["ep"].effects["target:2"] = pending  # a finished effect never regresses
    ctx3 = await EpisodeCtx.open(store, "ep", run_id="r", rng_seed=7)
    async with httpx.AsyncClient() as c:
        t3 = make(conf, c)
        await t3.open(ctx3)
        await t3.send(ctx3, "one")
        await t3.send(ctx3, "two")
        with pytest.raises(IndeterminateEffect):
            await t3.send(ctx3, "three")


async def test_retry_and_fail_fast(fake):
    async with httpx.AsyncClient() as c:
        t = make(cfg(fake.base_url + "/agent"), c)
        ctx = await make_ctx()
        await t.open(ctx)
        fake.failures = [503, 429]
        assert await t.send(ctx, "a") == "got: a"
        fake.failures = [404]
        with pytest.raises(TargetError) as e:
            await t.send(ctx, "b")
        assert e.value.code == "http_404"
        fake.failures = [500] * 9
        with pytest.raises(TargetError) as e2:
            await t.send(ctx, "c")
        assert e2.value.code == "unreachable"


async def test_missing_secret_and_secret_header(fake):
    conf = cfg(fake.base_url + "/agent", headers={"X-Key": "{{secret:API}}"})
    async with httpx.AsyncClient() as c:
        ctx = await make_ctx()
        t = make(conf, c)
        await t.open(ctx)
        with pytest.raises(TargetError) as e:
            await t.send(ctx, "x")
        assert e.value.code == "missing_secret"
        t2 = make(conf, c, {"API": "s3cret"})
        await t2.open(ctx)
        await t2.send(ctx, "x")
    assert fake.requests[0]["headers"]["x-key"] == "s3cret"


async def test_non_json_and_missing_reply_path(fake):
    async with httpx.AsyncClient() as c:
        ctx = await make_ctx()
        t = make(cfg(fake.base_url + "/plain"), c)
        await t.open(ctx)
        with pytest.raises(TargetError) as e:
            await t.send(ctx, "x")
        assert e.value.code == "bad_reply"
        t2 = make(cfg(fake.base_url + "/agent", reply_path="nope.x"), c)
        await t2.open(ctx)
        with pytest.raises(TargetError) as e2:
            await t2.send(ctx, "x")
        assert e2.value.code == "bad_reply"


def test_method_validated_at_construction():
    with pytest.raises(ValueError):
        HttpTarget(
            cfg("http://x", method="DELETE"), secrets={}, client=httpx.AsyncClient(), safety=POLICY
        )
