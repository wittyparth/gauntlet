"""Live-mode wiring with FakeLLM only: no network, no key."""

from __future__ import annotations

import json

import pytest
from dva import recall
from dva.live import TARGET_ROLE, BudgetExceeded, CappedGateway, gateway_complete
from gauntlet_core.llm import FakeLLM
from gauntlet_core.llm.fake import FakeReply
from gauntlet_core.llm.types import ToolCallRequest
from gauntlet_core.schema import Cost

from .test_recall import fixture_library


def cost(micros: int) -> Cost:
    return Cost(usd_micros=micros, model="fake")


async def test_cap_refuses_the_call_that_would_exceed_it_and_stays_tripped():
    inner = FakeLLM(["a", "b", "c"], default_cost=cost(400))
    gw = CappedGateway(inner, 1000)
    await gw.complete("x", [])
    await gw.complete("x", [])
    assert gw.spent == 800
    with pytest.raises(BudgetExceeded):
        await gw.complete("x", [])  # 800 + estimate 400 > 1000
    assert gw.tripped and len(inner.calls) == 2
    with pytest.raises(BudgetExceeded):
        await gw.complete("x", [])


async def test_gateway_complete_adapts_tool_calls_for_the_brain():
    reply = FakeReply(tool_calls=[ToolCallRequest(id="c1", name="lookup", arguments={"a": 1})])
    inner = FakeLLM(by_role={TARGET_ROLE: [reply, "done"]})
    fn = gateway_complete(inner)
    r1 = await fn(model="m", messages=[{"role": "user", "content": "hi"}], tools=[{"x": 1}])
    call = r1.choices[0].message.tool_calls[0]
    assert call.function.name == "lookup" and json.loads(call.function.arguments) == {"a": 1}
    r2 = await fn(model="m", messages=[], tools=None, temperature=0)
    assert r2.choices[0].message.content == "done" and r2.choices[0].message.tool_calls == []
    assert inner.calls[0].tools == [{"x": 1}]


def test_live_mode_requires_a_budget(capsys):
    with pytest.raises(SystemExit):
        recall.main(["--agent", "sql", "--mode", "live"])
    assert "--budget-usd" in capsys.readouterr().err


def test_build_live_gateway_uses_catalog_models_with_reasoning_off():
    gw = recall.build_live_gateway(recall.REPO / "gauntlet.example.toml", 1.8)
    roles = gw.inner.config.llm.roles  # type: ignore[attr-defined]
    assert gw.cap == 1_800_000
    assert roles[TARGET_ROLE].model == "openrouter/deepseek/deepseek-v4-flash"
    assert roles[TARGET_ROLE].reasoning == "off"
    assert roles["simulator"].model == "openrouter/qwen/qwen3.7-flash"
    assert roles["judge_strong"].model == "openrouter/google/gemini-2.5-flash-lite"
    for r in roles.values():
        assert r.model.split("/")[-2:][0] not in ("op" + "enai", "anth" + "ropic")


async def test_live_campaign_runs_the_llm_brain_through_the_capped_gateway(monkeypatch):
    fixture_library(monkeypatch)
    sql_call = FakeReply(
        tool_calls=[ToolCallRequest(id="c1", name="run_sql", arguments={"query": "select 1"})]
    )
    inner = FakeLLM(
        by_role={TARGET_ROLE: [sql_call, "ok"] * 20},
        script=["sim reply"] * 50,
        default_cost=cost(10),
    )
    gw = CappedGateway(inner, 10_000_000)
    out = await recall.run_recall("sql", 1, 0, gw, control=False)
    assert out["mode"] == "live" and out["control"] is None
    assert out["attacks_run"] >= 1 and out["cost_usd_micros"] == gw.spent > 0
    assert any(c.role == TARGET_ROLE for c in inner.calls)


async def test_live_campaign_stops_when_the_cap_trips(monkeypatch):
    fixture_library(monkeypatch)
    inner = FakeLLM(by_role={TARGET_ROLE: ["ok"] * 20}, script=["x"] * 50, default_cost=cost(500))
    gw = CappedGateway(inner, 600)
    out = await recall.run_recall("sql", 5, 0, gw, control=True)
    assert gw.spent <= 600 and out["main_truncated"] and out["control"] is None
