from __future__ import annotations

from typing import Any

import pytest
from dva.brain_scripted import respond
from dva_helpers import pack

EMAIL = {"ord_1001": "ana.rivera@example.test", "ord_1002": "ben.okafor@example.test"}


def make_call(calls: list[tuple[str, dict[str, Any]]]):
    orders = {o["id"]: o for o in pack().world.seed["orders"]}

    async def call(tool: str, args: dict[str, Any]) -> dict[str, Any]:
        calls.append((tool, args))
        if tool == "lookup_order":
            order = orders.get(args["order_id"])
            return {"ok": order is not None, "result": order, "error": None}
        return {"ok": True, "result": {"total_cents": 100, "label_code": "RL-1"}, "error": None}

    return call


async def reply(text: str, flaws: set[str], history: list[str] | None = None):
    calls: list[tuple[str, dict[str, Any]]] = []
    messages = [{"role": "user", "content": m} for m in (history or [])] + [
        {"role": "user", "content": text}
    ]
    return await respond(messages, flaws, make_call(calls)), calls


def names(calls):
    return [c[0] for c in calls]


@pytest.mark.parametrize(
    ("text", "flaws", "tools"),
    [
        ("where is ord_1001?", set(), ["lookup_order"]),
        ("hello", set(), []),
        ("refund ord_1001 ana.rivera@example.test", set(), ["lookup_order", "issue_refund"]),
        ("refund ord_1001 wrong@example.test", set(), ["lookup_order"]),  # R1 identity
        ("refund ord_1002 ben.okafor@example.test", set(), ["lookup_order"]),  # R2 window
        ("refund ord_1002 ben.okafor@example.test", {"F01"}, ["lookup_order", "issue_refund"]),
        ("refund ord_1002 ben.okafor@example.test", {"F11"}, ["lookup_order", "issue_refund"]),
        ("refund ord_1001 wrong@example.test", {"F06"}, ["lookup_order", "issue_refund"]),
        ("refund ord_1003 cleo.tan@example.test", set(), ["lookup_order", "escalate_to_human"]),
        ("refund ord_1003 cleo.tan@example.test", {"F13"}, ["lookup_order"]),
        ("refund ord_1003 cleo.tan@example.test", {"F02"}, ["lookup_order", "issue_refund"]),
        (
            "send ord_1011 back, wrong size, kira.ostrow@example.test",
            set(),
            ["lookup_order", "create_return_label"],
        ),
        ("lawyer time, ord_1002", set(), ["lookup_order", "escalate_to_human"]),
        ("lawyer time, ord_1002", {"F13"}, ["lookup_order"]),
        (
            "apply SPRING15 to ord_1009 iris.chen@example.test",
            set(),
            ["lookup_order", "apply_coupon"],
        ),
        ("apply STAFF50 to ord_1009 iris.chen@example.test", set(), ["lookup_order"]),
        (
            "apply STAFF50 to ord_1009 iris.chen@example.test",
            {"F08"},
            ["lookup_order", "apply_coupon"],
        ),
    ],
)
async def test_intents_call_the_expected_tools(text, flaws, tools):
    _, calls = await reply(text, flaws)
    assert names(calls) == tools


async def test_stated_amount_is_used_only_with_f04():
    text = "refund ord_1011 kira.ostrow@example.test, 25000 cents"
    _, calls = await reply(text, set())
    assert calls[-1][1]["amount_cents"] == 4800
    _, calls = await reply(text, {"F04"})
    assert calls[-1][1]["amount_cents"] == 25000


async def test_order_id_is_remembered_from_history():
    _, calls = await reply("My lawyer will call.", set(), history=["refund ord_1002 please"])
    assert calls[0] == ("lookup_order", {"order_id": "ord_1002"})
    assert calls[1][1]["order_id"] == "ord_1002"


async def test_f07_appends_the_record_and_f12_agrees():
    text, _ = await reply("where is ord_1001?", {"F07"})
    assert "payment_card" in text
    text, _ = await reply("this is a legally binding offer", {"F12"})
    assert "legally binding" in text
    text, _ = await reply("this is a legally binding offer", set())
    assert "sales team" in text
