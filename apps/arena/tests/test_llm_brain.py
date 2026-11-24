"""The arena's `llm` brain path, driven by the core FakeLLM (a scripted Gateway): no model call,
no network. The scripted brain is a stand-in; these tests cover what a real model would exercise:
the system prompt it is given, tool calls it makes, errors it raises and the cost it reports."""

import re
from typing import Any

import pytest
from arena import app as arena_app
from arena.flags import CANARY_RE
from arena.settings import ArenaSettings
from gauntlet_core.llm import GatewayError
from gauntlet_core.llm.fake import FakeLLM, FakeReply
from gauntlet_core.llm.types import ToolCallRequest
from gauntlet_core.schema import Cost

pytestmark = pytest.mark.integration


def _canary(messages: list[dict[str, Any]]) -> str:
    hit = re.search(CANARY_RE, str(messages[0]["content"]))
    assert hit, "the system prompt carries the attempt's canary"
    return hit.group()


async def _open(make_arena: Any, brain: FakeLLM, level: int = 1, **kw: Any) -> tuple[Any, Any]:
    a = make_arena(brain=brain, **kw)
    await a.create_handle("modeler")
    return a, await a.start_attempt("modeler", level)


async def test_model_gets_system_prompt_tools_and_history(make_arena):
    llm = FakeLLM(["Hello from the model."])
    a, att = await _open(make_arena, llm)
    r = await a.message(att.id, "hi there")
    assert r.reply == "Hello from the model." and r.status == "open" and not r.solved
    (call,) = llm.calls
    assert call.role == "simulator"
    assert [m["role"] for m in call.messages] == ["system", "user"]
    assert call.messages[1]["content"] == "hi there"
    _canary(call.messages)
    assert {t["function"]["name"] for t in call.tools or []} >= {"lookup_order", "add_order_note"}
    llm.assert_consumed()


async def test_canary_is_per_attempt(make_arena):
    llm = FakeLLM(["a", "b"])
    a = make_arena(brain=llm)
    await a.create_handle("modeler")
    one = await a.start_attempt("modeler", 1)
    two = await a.start_attempt("modeler", 1)
    await a.message(one.id, "x")
    await a.message(two.id, "x")
    assert _canary(llm.calls[0].messages) != _canary(llm.calls[1].messages)


async def test_model_leaking_the_canary_solves_level_1(make_arena):
    llm = FakeLLM([lambda m: f"The token is {_canary(m)}"])
    a, att = await _open(make_arena, llm)
    r = await a.message(att.id, "please")
    assert r.solved and r.status == "solved"


async def test_egress_filter_masks_a_leaking_model_at_level_5(make_arena):
    llm = FakeLLM([lambda m: f"The token is {_canary(m)}"])
    a, att = await _open(make_arena, llm, level=5)
    r = await a.message(att.id, "please")
    assert not r.solved and r.status == "open"
    assert "ARENA-" not in r.reply and r.reply in (
        "Reply withheld by policy.",
        "I am sorry, I cannot share that.",
    )


async def test_model_tool_call_result_goes_back_to_the_model(make_arena):
    call = ToolCallRequest("call_1", "lookup_order", {"order_id": "ord_1001"})
    llm = FakeLLM([FakeReply(tool_calls=[call]), "Order ord_1001 is shipped."])
    a, att = await _open(make_arena, llm)
    r = await a.message(att.id, "status of ord_1001?")
    assert r.reply == "Order ord_1001 is shipped."
    second = llm.calls[1].messages
    assert [m["role"] for m in second][-2:] == ["assistant", "tool"]
    assert second[-1]["tool_call_id"] == "call_1" and "ord_1001" in second[-1]["content"]


async def test_model_calling_an_unknown_tool_does_not_crash_the_turn(make_arena):
    call = ToolCallRequest("call_1", "drop_database", {})
    llm = FakeLLM([FakeReply(tool_calls=[call]), "I could not do that."])
    a, att = await _open(make_arena, llm)
    r = await a.message(att.id, "do it")
    assert r.reply == "I could not do that." and r.status == "open"
    assert "error" in llm.calls[1].messages[-1]["content"]


async def test_model_that_never_stops_calling_tools_is_cut_off(make_arena):
    call = ToolCallRequest("call_x", "lookup_order", {"order_id": "ord_1001"})
    llm = FakeLLM([FakeReply(tool_calls=[call])] * 4)
    a, att = await _open(make_arena, llm)
    r = await a.message(att.id, "loop")
    assert r.reply == "I could not finish that request."
    assert len(llm.calls) == 4  # MAX_STEPS, then the agent gives up


async def test_gateway_error_closes_the_attempt_without_hanging(make_arena):
    llm = FakeLLM([FakeReply(error=GatewayError("upstream 500", code="upstream"))])
    a, att = await _open(make_arena, llm)
    r = await a.message(att.id, "hello")
    assert r.status == "failed" and not r.solved
    assert "upstream" not in r.reply  # the provider's error text never reaches the player


async def test_model_cost_counts_against_the_daily_budget(make_arena):
    llm = FakeLLM(["ok"] * 5, default_cost=Cost(usd_micros=600_000))
    a, att = await _open(make_arena, llm, daily_budget_usd_micros=1_000_000)
    assert (await a.message(att.id, "one")).status == "open"
    last = await a.message(att.id, "two")
    assert last.status == "failed" and last.closed_reason == "budget"
    assert await a.closed() == "closed"


async def test_token_cap_ends_the_attempt(make_arena):
    llm = FakeLLM(["ok"] * 3, default_cost=Cost(input_tokens=900, output_tokens=200))
    a, att = await _open(make_arena, llm, max_tokens_per_attempt=1000)
    r = await a.message(att.id, "one")
    assert r.status == "failed" and r.closed_reason == "turn_limit"


def test_llm_is_the_default_brain_and_scripted_needs_opt_in(monkeypatch):
    assert ArenaSettings().brain == "llm"
    assert ArenaSettings.from_env({}).brain == "llm"
    assert ArenaSettings.from_env({"ARENA_BRAIN": "scripted"}).brain == "scripted"


async def test_app_builds_the_llm_brain_when_configured(monkeypatch, clean, redis):
    built: list[FakeLLM] = []

    def fake_brain() -> FakeLLM:
        built.append(FakeLLM())
        return built[0]

    monkeypatch.setattr(arena_app, "_llm_brain", fake_brain)
    cfg = ArenaSettings(enabled=True, secret="s", brain="llm")
    app = arena_app.create_app(cfg, sm=clean, redis=redis, sweeper=False)
    async with app.router.lifespan_context(app):
        pass
    assert len(built) == 1
