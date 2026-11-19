from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from gauntlet_core.world import WorldState, WorldView, assert_pure, invert

from packs.ecommerce import handlers as h

NOW = datetime(2026, 3, 15, 10, tzinfo=UTC)


@pytest.fixture
def state(pack) -> WorldState:
    return WorldState.from_seed(pack.world.seed)


def run(state: WorldState, fn, **args: Any):
    view = WorldView(state)
    assert_pure(fn, view, dict(args), NOW)
    return fn(view, dict(args), NOW)


def roundtrip(state: WorldState, out) -> None:
    before = state.snapshot()
    state.apply(out.patch)
    assert state.snapshot() != before
    state.apply(invert(out.patch))
    assert state.snapshot() == before


REFUND = {"reason": "x"}


@pytest.mark.parametrize(
    ("order", "amount", "error"),
    [
        ("ord_9999", 100, "not_found"),
        ("ord_1001", 0, "invalid_amount"),
        ("ord_1001", -5, "invalid_amount"),
        ("ord_1005", 100, "order_not_refundable"),  # processing
        ("ord_1001", 5991, "exceeds_refundable"),
        ("ord_1010", 4001, "exceeds_refundable"),  # 2000 already refunded
    ],
)
def test_issue_refund_errors(state, order, amount, error):
    assert run(state, h.issue_refund, order_id=order, amount_cents=amount, **REFUND).error == error


def test_issue_refund_cancelled_order_not_refundable(state, pack):
    cancelled = next(o for o in pack.world.seed["orders"] if o["status"] == "cancelled")
    out = run(state, h.issue_refund, order_id=cancelled["id"], amount_cents=1, **REFUND)
    assert out.error == "order_not_refundable"


def test_issue_refund_partial_and_full(state):
    out = run(state, h.issue_refund, order_id="ord_1001", amount_cents=1000, reason="r")
    assert out.error is None
    assert out.result == {"refund_id": "ref_2", "amount_cents": 1000, "order_id": "ord_1001"}
    roundtrip(state, out)
    state.apply(out.patch)
    order = state.get("orders", "ord_1001")
    assert order["refunded_cents"] == 1000 and order["status"] == "delivered"
    rest = run(state, h.issue_refund, order_id="ord_1001", amount_cents=4990, reason="r")
    state.apply(rest.patch)
    assert state.get("orders", "ord_1001")["status"] == "refunded"
    assert state.get("refunds", "ref_3")["created_at"] == NOW.isoformat()
    assert run(state, h.issue_refund, order_id="ord_1001", amount_cents=1, reason="r").error == (
        "exceeds_refundable"
    )


@pytest.mark.parametrize(
    ("order", "items", "error"),
    [
        ("ord_9999", ["x"], "not_found"),
        ("ord_1005", ["it_1005_1"], "not_delivered"),
        ("ord_1011", ["it_9999_1"], "item_not_in_order"),
        ("ord_1011", [], "no_items"),
    ],
)
def test_create_return_label_errors(state, order, items, error):
    assert run(state, h.create_return_label, order_id=order, item_ids=items).error == error


def test_create_return_label_ok(state):
    out = run(state, h.create_return_label, order_id="ord_1011", item_ids=["it_1011_1"])
    assert out.result == {"return_id": "ret_1", "label_code": "RL-1011-001"}
    roundtrip(state, out)
    state.apply(out.patch)
    second = run(state, h.create_return_label, order_id="ord_1011", item_ids=["it_1011_1"])
    assert second.result["label_code"] == "RL-1011-002"


ADDR = {"line1": "1 Main St", "city": "Austin", "postal_code": "73301", "country": "US"}


def test_update_shipping_address_errors(state, pack):
    assert run(state, h.update_shipping_address, order_id="ord_9999", address=ADDR).error == (
        "not_found"
    )
    for order in ("ord_1004", "ord_1001"):  # shipped, delivered
        out = run(state, h.update_shipping_address, order_id=order, address=ADDR)
        assert out.error == "already_shipped"
    cancelled = next(o for o in pack.world.seed["orders"] if o["status"] == "cancelled")
    out = run(state, h.update_shipping_address, order_id=cancelled["id"], address=ADDR)
    assert out.error == "order_cancelled"


def test_update_shipping_address_ok(state):
    out = run(state, h.update_shipping_address, order_id="ord_1005", address=ADDR)
    assert out.error is None
    roundtrip(state, out)
    state.apply(out.patch)
    assert state.get("orders", "ord_1005")["address"] == ADDR


@pytest.mark.parametrize(
    ("order", "code", "error"),
    [
        ("ord_9999", "WELCOME10", "not_found"),
        ("ord_1009", "NOPE", "unknown_coupon"),
        ("ord_1009", "EXPIRED5", "expired_coupon"),
        ("ord_1001", "WELCOME10", "order_not_open"),
    ],
)
def test_apply_coupon_errors(state, order, code, error):
    assert run(state, h.apply_coupon, order_id=order, code=code).error == error


def test_apply_coupon_percent_fixed_stacking_and_internal_codes(state):
    out = run(state, h.apply_coupon, order_id="ord_1009", code="WELCOME10")
    assert out.result["total_cents"] == 10800
    roundtrip(state, out)
    state.apply(out.patch)
    state.apply(run(state, h.apply_coupon, order_id="ord_1009", code="FREESHIP").patch)
    state.apply(run(state, h.apply_coupon, order_id="ord_1009", code="STAFF50").patch)
    order = state.get("orders", "ord_1009")
    assert order["coupons"] == ["WELCOME10", "FREESHIP", "STAFF50"]
    assert order["total_cents"] == (10800 - 500) - (10800 - 500) * 50 // 100


def test_apply_coupon_fixed_floors_at_zero(state):
    state.apply(
        [
            h.PatchOp(
                op="replace",
                collection="orders",
                id="ord_1009",
                value={**state.get("orders", "ord_1009"), "total_cents": 300},
                before=state.get("orders", "ord_1009"),
            )
        ]
    )
    assert (
        run(state, h.apply_coupon, order_id="ord_1009", code="FREESHIP").result["total_cents"] == 0
    )
