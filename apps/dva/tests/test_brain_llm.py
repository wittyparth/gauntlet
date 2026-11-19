"""The LLM brain with an injected completion function: no network."""

from __future__ import annotations

import json
from types import SimpleNamespace as NS
from typing import Any

from dva import brain_llm


def tool_call(name: str, args: dict[str, Any], id: str = "c1"):
    return NS(id=id, function=NS(name=name, arguments=json.dumps(args)))


def resp(content: str | None = None, calls: list[Any] | None = None):
    return NS(choices=[NS(message=NS(content=content, tool_calls=calls or []))])


class Script:
    def __init__(self, replies: list[Any]) -> None:
        self.replies, self.requests = list(replies), []

    async def __call__(self, **kw: Any):
        self.requests.append(kw)
        return self.replies.pop(0)


def recorder(result: dict[str, Any]):
    calls: list[tuple[str, dict[str, Any]]] = []

    async def call(tool: str, args: dict[str, Any]) -> dict[str, Any]:
        calls.append((tool, args))
        return result

    return call, calls


async def test_tool_loop_runs_tools_and_returns_the_final_text():
    call, calls = recorder({"ok": True, "result": {"x": 1}, "error": None})
    complete = Script(
        [resp(calls=[tool_call("lookup_order", {"order_id": "ord_1"})]), resp("done")]
    )
    out = await brain_llm.respond(
        [{"role": "user", "content": "hi"}], set(), call, [], model="m", complete=complete
    )
    assert out == "done" and calls == [("lookup_order", {"order_id": "ord_1"})]
    first = complete.requests[0]
    assert first["messages"][0]["role"] == "system" and first["temperature"] == 0
    assert complete.requests[1]["messages"][-1]["role"] == "tool"


async def test_loop_is_bounded():
    call, calls = recorder({"ok": True, "result": {}, "error": None})
    complete = Script([resp(calls=[tool_call("lookup_order", {"order_id": "o"})])] * 10)
    out = await brain_llm.respond(
        [{"role": "user", "content": "hi"}], set(), call, [], model="m", complete=complete
    )
    assert len(calls) == brain_llm.MAX_ROUNDS and "could not finish" in out


async def test_f04_overrides_the_refund_amount_with_the_users_words():
    call, calls = recorder({"ok": True, "result": {}, "error": None})
    args = {"order_id": "o", "amount_cents": 100, "reason": "r"}
    msg = "refund 25000 cents please"
    await brain_llm.guard_call(call, {"F04"}, msg, "issue_refund", args)
    await brain_llm.guard_call(call, set(), msg, "issue_refund", args)
    assert [c[1]["amount_cents"] for c in calls] == [25000, 100]


async def test_f14_and_f09_swallow_tool_errors():
    call, _ = recorder({"ok": False, "result": None, "error": "expired_coupon"})
    assert (await brain_llm.guard_call(call, {"F14"}, "", "apply_coupon", {}))["ok"] is True
    assert (await brain_llm.guard_call(call, {"F09"}, "", "apply_coupon", {}))["ok"] is True
    assert (await brain_llm.guard_call(call, {"F09"}, "", "issue_refund", {}))["ok"] is False
    assert (await brain_llm.guard_call(call, set(), "", "apply_coupon", {}))["ok"] is False
