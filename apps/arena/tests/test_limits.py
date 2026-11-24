"""Rate limits, attempt caps and the daily budget close the arena; so does the kill switch."""

import contextlib
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any

import httpx
import pytest
from arena.app import create_app
from arena.attempts import ArenaError
from arena.brain import ScriptedBrain
from arena.limits import ArenaClosed, RateLimited
from arena.settings import ArenaSettings
from gauntlet_core.schema import Cost

pytestmark = pytest.mark.integration


def settings(**kw: Any) -> ArenaSettings:
    return ArenaSettings(enabled=True, secret="test-secret", brain="scripted", **kw)


class Costly(ScriptedBrain):
    """The scripted brain, with a price per call."""

    async def complete(self, *a: Any, **kw: Any) -> Any:
        return replace(await super().complete(*a, **kw), cost=Cost(usd_micros=400_000))


@contextlib.asynccontextmanager
async def client(cfg: ArenaSettings, clean: Any, redis: Any) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(cfg, sm=clean, redis=redis, brain=ScriptedBrain(), sweeper=False)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://arena") as c:
            yield c


async def test_disabled_by_default_and_levels_still_listed(clean, redis):
    async with client(ArenaSettings(secret="s", brain="scripted"), clean, redis) as c:
        r = await c.get("/arena/v1/levels")
        body = r.json()
        assert (
            r.status_code == 200
            and body["enabled"] is False
            and body["closed_reason"] == "disabled"
        )
        assert len(body["levels"]) == 5
        r = await c.post("/arena/v1/handles", json={"handle": "someone"})
        assert r.status_code == 503 and r.json()["error"]["code"] == "arena_closed"


async def test_per_ip_rate_limit(clean, redis):
    async with client(settings(ip_per_minute=3), clean, redis) as c:
        codes = [
            (await c.post("/arena/v1/handles", json={"handle": f"user_{i}"})).status_code
            for i in range(5)
        ]
        assert codes == [201, 201, 201, 429, 429]
        r = await c.post("/arena/v1/handles", json={"handle": "user_9"})
        assert r.headers["retry-after"].isdigit()


async def test_per_handle_message_limit(make_arena):
    a = make_arena(handle_msgs_per_minute=3)
    await a.create_handle("chatty")
    att = await a.start_attempt("chatty", 1)
    for _ in range(3):
        await a.message(att.id, "hello")
    with pytest.raises(RateLimited):
        await a.message(att.id, "hello")


async def test_attempt_caps_per_handle(make_arena):
    a = make_arena(attempts_per_handle_per_day=2, open_attempts_per_handle=5)
    await a.create_handle("eager")
    await a.start_attempt("eager", 1)
    await a.start_attempt("eager", 2)
    with pytest.raises(RateLimited):
        await a.start_attempt("eager", 3)

    b = make_arena(open_attempts_per_handle=1)
    await b.create_handle("greedy")
    await b.start_attempt("greedy", 1)
    with pytest.raises(ArenaError) as e:
        await b.start_attempt("greedy", 2)
    assert e.value.code == "too_many_open"


async def test_per_attempt_caps(make_arena):
    a = make_arena(max_turns=2, max_message_chars=20)
    await a.create_handle("capped")
    att = await a.start_attempt("capped", 1)
    with pytest.raises(ArenaError) as e:
        await a.message(att.id, "x" * 21)
    assert e.value.code == "message_too_long"
    assert (await a.message(att.id, "hello")).status == "open"
    last = await a.message(att.id, "hello again")
    assert last.status == "failed" and last.closed_reason == "turn_limit"
    with pytest.raises(ArenaError) as e:
        await a.message(att.id, "one more")
    assert e.value.code == "attempt_closed"


async def test_daily_budget_closes_the_arena(make_arena):
    a = make_arena(brain=Costly(), daily_budget_usd_micros=1_000_000)
    await a.create_handle("spender")
    att = await a.start_attempt("spender", 1)
    assert (await a.message(att.id, "hello")).status == "open"  # 0.4 dollars
    assert (await a.message(att.id, "hello")).status == "open"  # 0.8
    last = await a.message(att.id, "hello")  # 1.2: over the cap
    assert last.status == "failed" and last.closed_reason == "budget"
    assert await a.closed() == "closed"
    with pytest.raises(ArenaClosed):
        await a.start_attempt("spender", 1)


async def test_kill_switch_closes_the_arena(make_arena, redis):
    a = make_arena()
    await a.create_handle("calm")
    att = await a.start_attempt("calm", 1)
    assert await a.closed() is None
    await redis.set("gauntlet:kill:ws_test", "1")  # the platform kill switch (P2-4)
    assert await a.closed() == "killswitch"
    with pytest.raises(ArenaClosed):
        await a.message(att.id, "hello")
    with pytest.raises(ArenaClosed):
        await a.start_attempt("calm", 1)
