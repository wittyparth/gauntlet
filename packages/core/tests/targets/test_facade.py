from __future__ import annotations

import asyncio

import httpx
import pytest
from gauntlet_core.engine import EpisodeCtx, MemoryJournalStore, SimTurn, run_episode
from gauntlet_core.schema import OpenAICompatTargetConfig
from gauntlet_core.targets import (
    LocalFacade,
    OpenAICompatTarget,
    UrlPolicy,
    mint_token,
    verify_token,
)
from gauntlet_core.world import World, build_world
from helpers import SPEC, scenario

SECRET = b"k" * 32


def test_token_roundtrip_and_tamper():
    tok = mint_token("ep.1", 3, SECRET)
    assert verify_token(tok, SECRET) == ("ep.1", 3)
    ep, _, sig = tok.rsplit(".", 2)
    for bad in (f"{ep}.4.{sig}", f"x{tok}", tok + "A", "garbage", ""):
        with pytest.raises(ValueError):
            verify_token(bad, SECRET)
    with pytest.raises(ValueError):
        verify_token(tok, b"other")


@pytest.fixture
async def facade():
    f = LocalFacade(secret=SECRET)
    await f.start()
    yield f
    await f.stop()


async def attached(facade: LocalFacade):
    store = MemoryJournalStore()
    ctx = await EpisodeCtx.open(store, "ep", run_id="r", rng_seed=7)
    world = World(build_world(SPEC, None, 7))
    ctx.state["world"] = world
    return store, ctx, facade.attach(ctx, world)


async def test_tools_listing_and_call(facade):
    store, ctx, token = await attached(facade)
    base = facade.base_url
    async with httpx.AsyncClient() as c:
        tools = (await c.get(f"{base}/mock/{token}/tools")).json()
        assert {t["function"]["name"] for t in tools} == {"lookup_order", "cancel_order"}
        r = await c.post(f"{base}/mock/{token}/tools/lookup_order", json={"order_id": "ord_1"})
        assert r.json()["ok"] is True and r.json()["result"]["status"] == "shipped"
        r = await c.post(f"{base}/mock/{token}/tools/nope", json={})
        assert r.status_code == 200
        assert r.json() == {"ok": False, "result": None, "error": "unknown_tool"}
        r = await c.post(
            f"{base}/mock/tools/lookup_order",
            json={"order_id": "ord_2"},
            headers={"X-Gauntlet-Episode": token},
        )
        assert r.json()["result"]["status"] == "new"
    await ctx.flush()
    events = (await store.load("ep")).events
    assert [e.payload["via"] for e in events if e.kind == "tool_call"] == ["wired"] * 3
    assert "tool:0" in (await store.load("ep")).effects


async def test_bad_token_401_and_mcp_501(facade):
    _, _, token = await attached(facade)
    base = facade.base_url
    async with httpx.AsyncClient() as c:
        assert (await c.get(f"{base}/mock/bad.1.sig/tools")).status_code == 401
        forged = mint_token("other", 1, b"z" * 32)
        assert (await c.get(f"{base}/mock/{forged}/tools")).status_code == 401
        assert (await c.get(f"{base}/mock/tools")).status_code == 401
        r = await c.post(f"{base}/mock/{token}/mcp", json={})
        assert r.status_code == 501 and r.json() == {"error": "not_implemented"}
    facade.detach(token)
    async with httpx.AsyncClient() as c:
        assert (await c.get(f"{base}/mock/{token}/tools")).status_code == 401


async def test_concurrent_calls_serialise(facade):
    store, ctx, token = await attached(facade)
    url = f"{facade.base_url}/mock/{token}/tools/lookup_order"
    async with httpx.AsyncClient() as c:
        rs = await asyncio.gather(*(c.post(url, json={"order_id": "ord_1"}) for _ in range(6)))
    assert all(r.json()["ok"] for r in rs)
    await ctx.flush()
    j = await store.load("ep")
    assert sorted(k for k in j.effects if k.startswith("tool:")) == [f"tool:{i}" for i in range(6)]
    assert [e.seq for e in j.events] == list(range(len(j.events)))


class Say:
    async def next_message(self, ctx):
        n = sum(1 for e in ctx.trajectory_so_far if e.kind == "user_message")
        return SimTurn("message", "status?") if n == 0 else SimTurn("done")


async def test_wired_fake_agent_calls_tool_through_facade(fake, facade):
    store = MemoryJournalStore()
    ctx = await EpisodeCtx.open(store, "ep", run_id="r", rng_seed=7)
    world = World(build_world(SPEC, None, 7))
    ctx.state["world"] = world
    cfg = OpenAICompatTargetConfig(base_url=fake.base_url + "/wired", model="m", wired=True)
    async with httpx.AsyncClient() as c:
        target = OpenAICompatTarget(
            cfg, secrets={}, client=c, safety=UrlPolicy(allow_private=True), facade=facade
        )
        res = await run_episode(ctx, scenario(), target, Say())
    assert res.outcome == "passed"  # reply contains "shipped"
    j = await store.load("ep")
    kinds = [e.kind for e in j.events]
    assert "tool_call" in kinds and kinds.index("tool_call") < kinds.index("agent_message")
    assert "tool:0" in j.effects and "target:0" in j.effects
    assert fake.requests[0]["headers"]["x-gauntlet-mock-base"] == facade.base_url
