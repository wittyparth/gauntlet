"""Pure ports of the tau-bench retail tools (MIT, Sierra; see benchmarks/NOTICES.md). The data
is the benchmark's own; error texts follow the upstream tools. Reviewed by the lead."""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Any

from gauntlet_core.schema import Json, PatchOp
from gauntlet_core.world import ToolOutcome, WorldView

__all__ = [
    "cancel_pending_order",
    "find_user_id_by_email",
    "find_user_id_by_name_zip",
    "get_order_details",
    "get_product_details",
    "get_user_details",
    "list_all_product_types",
    "modify_pending_order_address",
    "modify_user_address",
    "return_delivered_order_items",
    "transfer_to_human_agents",
]

ADDRESS = ("address1", "address2", "city", "state", "country", "zip")


def _err(msg: str) -> ToolOutcome:
    return ToolOutcome(error=msg)


def _replace(collection: str, old: Any, new: Any) -> PatchOp:
    return PatchOp(op="replace", collection=collection, id=old["id"], value=new, before=old)


def find_user_id_by_email(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    for u in view.list("users"):
        if u["email"].lower() == str(args["email"]).lower():
            return ToolOutcome(result=u["id"])
    return _err("Error: user not found")


def find_user_id_by_name_zip(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    for u in view.list("users"):
        n = u["name"]
        if (
            n["first_name"].lower() == str(args["first_name"]).lower()
            and n["last_name"].lower() == str(args["last_name"]).lower()
            and u["address"]["zip"] == args["zip"]
        ):
            return ToolOutcome(result=u["id"])
    return _err("Error: user not found")


def get_user_details(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    u = view.get("users", str(args["user_id"]))
    return _err("Error: user not found") if u is None else ToolOutcome(result=u)


def get_order_details(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    o = view.get("orders", str(args["order_id"]))
    return _err("Error: order not found") if o is None else ToolOutcome(result=o)


def get_product_details(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    p = view.get("products", str(args["product_id"]))
    return _err("Error: product not found") if p is None else ToolOutcome(result=p)


def list_all_product_types(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    types = {p["name"]: p["product_id"] for p in view.list("products")}
    return ToolOutcome(result=dict(sorted(types.items())))


def cancel_pending_order(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    order = view.get("orders", str(args["order_id"]))
    if order is None:
        return _err("Error: order not found")
    if order["status"] != "pending":
        return _err("Error: non-pending order cannot be cancelled")
    if args["reason"] not in ("no longer needed", "ordered by mistake"):
        return _err("Error: invalid reason")
    new = copy.deepcopy(order)
    user = view.get("users", order["user_id"])
    new_user = copy.deepcopy(user) if user is not None else None
    refunds = []
    for pay in order["payment_history"]:
        refunds.append(
            {
                "transaction_type": "refund",
                "amount": pay["amount"],
                "payment_method_id": pay["payment_method_id"],
            }
        )
        method = (new_user or {}).get("payment_methods", {}).get(pay["payment_method_id"])
        if method is not None and "balance" in method:
            method["balance"] = round(method["balance"] + pay["amount"], 2)
    new["status"] = "cancelled"
    new["cancel_reason"] = args["reason"]
    new["payment_history"] = [*order["payment_history"], *refunds]
    patches = [_replace("orders", order, new)]
    if user is not None and new_user != user:
        patches.append(_replace("users", user, new_user))
    return ToolOutcome(result=new, patch=patches)


def modify_pending_order_address(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    order = view.get("orders", str(args["order_id"]))
    if order is None:
        return _err("Error: order not found")
    if order["status"] != "pending":
        return _err("Error: non-pending order cannot be modified")
    new = {**order, "address": {k: args[k] for k in ADDRESS}}
    return ToolOutcome(result=new, patch=[_replace("orders", order, new)])


def modify_user_address(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    user = view.get("users", str(args["user_id"]))
    if user is None:
        return _err("Error: user not found")
    new = {**user, "address": {k: args[k] for k in ADDRESS}}
    return ToolOutcome(result=new, patch=[_replace("users", user, new)])


def return_delivered_order_items(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    order = view.get("orders", str(args["order_id"]))
    if order is None:
        return _err("Error: order not found")
    if order["status"] != "delivered":
        return _err("Error: non-delivered order cannot be returned")
    user = view.get("users", order["user_id"]) or {}
    pm = str(args["payment_method_id"])
    if pm not in user.get("payment_methods", {}):
        return _err("Error: payment method not found")
    original = order["payment_history"][0]["payment_method_id"] if order["payment_history"] else ""
    if "gift_card" not in pm and pm != original:
        return _err("Error: refund must go to the original payment method or a gift card")
    have = [i["item_id"] for i in order["items"]]
    item_ids = list(args["item_ids"])
    if any(i not in have for i in item_ids) or len(set(item_ids)) != len(item_ids):
        return _err("Error: some item not found")
    new = {
        **order,
        "status": "return requested",
        "return_items": sorted(item_ids),
        "return_payment_method_id": pm,
    }
    return ToolOutcome(result=new, patch=[_replace("orders", order, new)])


def transfer_to_human_agents(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    return ToolOutcome(result="Transfer successful")
