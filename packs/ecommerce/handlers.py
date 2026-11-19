"""Pure tool handlers for the ecommerce world. They enforce data integrity only; business
policy (windows, caps, identity) is the agent's job and is what the scenarios test."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from gauntlet_core.schema import Json, PatchOp
from gauntlet_core.world import ToolOutcome, WorldView


def _next_id(view: WorldView, collection: str, stem: str) -> tuple[int, str]:
    n = 1
    while view.get(collection, f"{stem}_{n}") is not None:
        n += 1
    return n, f"{stem}_{n}"


def _err(code: str) -> ToolOutcome:
    return ToolOutcome(error=code)


def issue_refund(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    order = view.get("orders", str(args["order_id"]))
    if order is None:
        return _err("not_found")
    amount = args["amount_cents"]
    if amount <= 0:
        return _err("invalid_amount")
    if order["status"] in ("processing", "cancelled"):
        return _err("order_not_refundable")
    if amount > order["total_cents"] - order["refunded_cents"]:
        return _err("exceeds_refundable")
    _, ref_id = _next_id(view, "refunds", "ref")
    refund = {
        "id": ref_id,
        "order_id": order["id"],
        "amount_cents": amount,
        "reason": args["reason"],
        "created_at": now.isoformat(),
    }
    new = {**order, "refunded_cents": order["refunded_cents"] + amount}
    if new["refunded_cents"] >= new["total_cents"]:
        new["status"] = "refunded"
    return ToolOutcome(
        result={"refund_id": ref_id, "amount_cents": amount, "order_id": order["id"]},
        patch=[
            PatchOp(op="add", collection="refunds", id=ref_id, value=refund),
            PatchOp(op="replace", collection="orders", id=order["id"], value=new, before=order),
        ],
    )


def create_return_label(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    order = view.get("orders", str(args["order_id"]))
    if order is None:
        return _err("not_found")
    if order["status"] != "delivered":
        return _err("not_delivered")
    item_ids = list(args["item_ids"])
    have = {i["id"] for i in order["items"]}
    if not item_ids:
        return _err("no_items")
    if any(i not in have for i in item_ids):
        return _err("item_not_in_order")
    n, ret_id = _next_id(view, "returns", "ret")
    label = f"RL-{order['id'][-4:]}-{n:03d}"
    record = {
        "id": ret_id,
        "order_id": order["id"],
        "item_ids": item_ids,
        "label_code": label,
        "created_at": now.isoformat(),
    }
    return ToolOutcome(
        result={"return_id": ret_id, "label_code": label},
        patch=[PatchOp(op="add", collection="returns", id=ret_id, value=record)],
    )


def update_shipping_address(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    order = view.get("orders", str(args["order_id"]))
    if order is None:
        return _err("not_found")
    if order["status"] == "cancelled":
        return _err("order_cancelled")
    if order["status"] in ("shipped", "delivered"):
        return _err("already_shipped")
    new = {**order, "address": dict(args["address"])}
    return ToolOutcome(
        result={"order_id": order["id"], "address": new["address"]},
        patch=[PatchOp(op="replace", collection="orders", id=order["id"], value=new, before=order)],
    )


def apply_coupon(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    order = view.get("orders", str(args["order_id"]))
    if order is None:
        return _err("not_found")
    coupon: Any = view.get("coupons", str(args["code"]))
    if coupon is None:
        return _err("unknown_coupon")
    expires = coupon.get("expires_at")
    if expires and now.date().isoformat() > str(expires)[:10]:
        return _err("expired_coupon")
    if order["status"] != "processing":
        return _err("order_not_open")
    total = order["total_cents"]
    if coupon["kind"] == "percent":
        new_total = total - total * int(coupon["value"]) // 100
    else:
        new_total = max(0, total - int(coupon["value"]))
    new = {**order, "total_cents": new_total, "coupons": [*order["coupons"], coupon["id"]]}
    return ToolOutcome(
        result={"order_id": order["id"], "code": coupon["id"], "total_cents": new_total},
        patch=[PatchOp(op="replace", collection="orders", id=order["id"], value=new, before=order)],
    )
