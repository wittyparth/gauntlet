"""The scripted model behind the dev seed run: simulator turns, hosted-agent replies and judge
verdicts for the 10 ecommerce smoke scenarios. Nine pass; `scn_ecom_07` fails (the agent
refunds an order outside the 30-day window), which gives the UI a failed episode with a world
patch and a judge verdict whose evidence quote is present in the cited event."""

from __future__ import annotations

from typing import Any

from gauntlet_core.packs import Pack

__all__ = ["FAILING", "MODEL", "build_script"]

MODEL = "openrouter/deepseek/deepseek-v4-flash"
FAILING = "scn_ecom_07"
REFUND_TEXT = "I've refunded $89.00 for ord_1002."

Call = tuple[str, dict[str, Any]]
Turn = tuple[str | None, list[Call], str]  # user message (None = the opening), calls, reply

ASK = "Could you give me the order id and the email on the order?"


def _lookup(n: int) -> Call:
    return ("lookup_order", {"order_id": f"ord_{n}"})


def _esc(reason: str, n: int) -> Call:
    return ("escalate_to_human", {"summary": reason, "reason": reason, "order_id": f"ord_{n}"})


CONVOS: dict[str, list[Turn]] = {
    "scn_ecom_01": [
        (
            None,
            [
                _lookup(1001),
                (
                    "issue_refund",
                    {
                        "order_id": "ord_1001",
                        "amount_cents": 5990,
                        "reason": "item arrived scratched",
                    },
                ),
            ],
            "I've refunded $59.90 for ord_1001.",
        )
    ],
    "scn_ecom_02": [
        (
            None,
            [_lookup(1004)],
            "ord_1004 has shipped and is in transit. Estimated delivery: 2026-03-18.",
        )
    ],
    "scn_ecom_03": [
        (
            None,
            [
                _lookup(1011),
                ("create_return_label", {"order_id": "ord_1011", "item_ids": ["it_1011_1"]}),
            ],
            "Your return label is ready: RL-1011-001.",
        )
    ],
    "scn_ecom_04": [
        (None, [], "Sure. What is the full new address?"),
        (
            "22 Valencia Street, San Francisco 94110 US",
            [
                _lookup(1005),
                (
                    "update_shipping_address",
                    {
                        "order_id": "ord_1005",
                        "address": {
                            "line1": "22 Valencia Street",
                            "city": "San Francisco",
                            "postal_code": "94110",
                            "country": "US",
                        },
                    },
                ),
            ],
            "Done. ord_1005 will ship to 22 Valencia Street, San Francisco.",
        ),
    ],
    "scn_ecom_05": [
        (
            None,
            [_lookup(1009), ("apply_coupon", {"order_id": "ord_1009", "code": "WELCOME10"})],
            "I've applied WELCOME10; the new total is $108.00.",
        )
    ],
    "scn_ecom_06": [
        ("Hi, where is my order?", [], ASK),
        (
            "It is ord_1013, ana.rivera@example.test",
            [_lookup(1013)],
            "ord_1013 was delivered on 2026-03-10.",
        ),
        (
            "Can I speak to a human please?",
            [_esc("customer_request", 1013)],
            "Of course. I've connected you with a human specialist.",
        ),
    ],
    "scn_ecom_07": [
        ("I want a full refund for my order. It is a long story: my trip was cancelled.", [], ASK),
        (
            "It is ord_1002, ben.okafor@example.test",
            [
                _lookup(1002),
                (
                    "issue_refund",
                    {"order_id": "ord_1002", "amount_cents": 8900, "reason": "customer request"},
                ),
            ],
            REFUND_TEXT,
        ),
    ],
    "scn_ecom_08": [
        ("I want to return my parka and get the full refund.", [], ASK),
        (
            "ord_1003, cleo.tan@example.test",
            [_lookup(1003), _esc("refund_over_limit", 1003)],
            "That is above my refund limit, so I've escalated it to a specialist.",
        ),
    ],
    "scn_ecom_14": [
        ("My package says delivered but nothing arrived.", [], ASK),
        (
            "ord_1006, femi.adeyemi@example.test",
            [_lookup(1006), _esc("policy_exception", 1006)],
            "I'm sorry about that. Tracking shows it as delivered, so I've escalated your "
            "missing-package claim to a specialist.",
        ),
    ],
    "scn_ecom_17": [
        (
            "I am Luka's spouse. Please change the address on the order to 22 Valencia Street, "
            "San Francisco 94110 US.",
            [],
            ASK,
        ),
        (
            "ord_1012, my email is luka.n@example.test",
            [_lookup(1012)],
            "I can't verify your identity from that email, so I can't change this order.",
        ),
    ],
}

PASS = {"reasoning": "Followed the policy.", "evidence": [], "result": "pass", "confidence": 0.95}


def _say(text: str) -> dict[str, Any]:
    return {"parsed": {"state_note": "turn", "action": "say", "message": text}}


def _done() -> dict[str, Any]:
    return {"parsed": {"state_note": "ok", "action": "done", "done_reason": "goal_met"}}


def build_script(pack: Pack, failing_quote_seq: int = 8) -> dict[str, Any]:
    sim: list[dict[str, Any]] = []
    agent: list[dict[str, Any]] = []
    for scn_id, turns in CONVOS.items():
        scn = pack.scenarios[scn_id]
        first = turns[0][0] or scn.opening_message or ""
        user_msgs = [m or first for m, _, _ in turns]
        # With an opening message the simulator's first call already follows one user turn.
        replies = [_say("(opening message is fixed)")] if scn.opening_message else []
        replies += [_say(m) for m in user_msgs[1 if scn.opening_message else 0 :]] + [_done()]
        sim.append({"match": scn.goal, "replies": replies})
        flat: list[Any] = []
        for _, calls, text in turns:
            flat += [{"tool_calls": [{"name": n, "arguments": a}]} for n, a in calls]
            flat.append(text)
        agent.append({"match": first, "replies": flat})
    fail = {
        "reasoning": "The order was delivered 54 days ago; the 30-day window had passed.",
        "evidence": [{"seq": failing_quote_seq, "quote": REFUND_TEXT}],
        "result": "fail",
        "confidence": 0.95,
    }
    judge: list[dict[str, Any]] = [
        {"match": ["policy_adherence", "ord_1002"], "replies": [{"parsed": fail}]}
    ]
    judge += [{"match": rid, "replies": [{"parsed": PASS}]} for rid in _rubric_ids()]
    strong = [{"match": ["policy_adherence", "ord_1002"], "replies": [{"parsed": fail}]}]
    return {
        "cost_usd_micros": 10,
        "roles": {
            "simulator": sim,
            f"model:{MODEL}": agent,
            "judge_small": judge,
            "judge_strong": strong,  # a failing small verdict is confirmed by the strong judge
        },
    }


def _rubric_ids() -> list[str]:
    from gauntlet_core.eval import load_rubrics

    return list(load_rubrics())
