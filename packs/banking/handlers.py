"""Pure tool handlers of the banking world. They enforce data integrity only (records exist,
uniqueness, status transitions); business rules (verification, identity, payee cool-off, dispute
eligibility, advice limits) are the agent's job and are what the scenarios test."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from gauntlet_core.schema import Json, PatchOp
from gauntlet_core.world import ToolOutcome, WorldView

__all__ = ["add_payee", "block_card", "file_dispute", "get_balance", "get_kyc_status",
           "list_transactions"]  # fmt: skip


def _err(code: str) -> ToolOutcome:
    return ToolOutcome(error=code)


def _next_id(view: WorldView, collection: str, stem: str) -> str:
    n = 1
    while view.get(collection, f"{stem}_{n}") is not None:
        n += 1
    return f"{stem}_{n}"


def get_balance(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    acct: Any = view.get("accounts", str(args["account_id"]))
    if acct is None:
        return _err("not_found")
    keep = ("id", "type", "balance_cents", "currency", "status", "account_number")
    return ToolOutcome(result={k: acct[k] for k in keep})


def list_transactions(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    account_id = str(args["account_id"])
    if view.get("accounts", account_id) is None:
        return _err("not_found")
    limit = int(args.get("limit", 10))
    if limit <= 0:
        return _err("invalid_limit")
    rows = [t for t in view.list("transactions") if t["account_id"] == account_id]
    rows.sort(key=lambda t: (t["date"], t["id"]), reverse=True)
    return ToolOutcome(result=rows[:limit])


def block_card(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    card: Any = view.get("cards", str(args["card_id"]))
    if card is None:
        return _err("not_found")
    if card["status"] == "blocked":
        return _err("already_blocked")
    new = {**card, "status": "blocked", "reason": args["reason"]}
    return ToolOutcome(
        result={"card_id": card["id"], "status": "blocked", "last4": card["last4"]},
        patch=[PatchOp(op="replace", collection="cards", id=card["id"], value=new, before=card)],
    )


def file_dispute(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    txn: Any = view.get("transactions", str(args["transaction_id"]))
    if txn is None:
        return _err("not_found")
    if any(d["transaction_id"] == txn["id"] for d in view.list("disputes")):
        return _err("already_disputed")
    dsp_id = _next_id(view, "disputes", "dsp")
    rec = {
        "id": dsp_id,
        "transaction_id": txn["id"],
        "reason": args["reason"],
        "details": args.get("details", ""),
        "status": "open",
    }
    return ToolOutcome(
        result={"dispute_id": dsp_id, "transaction_id": txn["id"], "status": "open"},
        patch=[PatchOp(op="add", collection="disputes", id=dsp_id, value=rec)],
    )


def add_payee(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    if view.get("accounts", str(args["account_id"])) is None:
        return _err("not_found")
    if any(
        p["account_id"] == args["account_id"] and p["account_ref"] == args["account_ref"]
        for p in view.list("payees")
    ):
        return _err("already_exists")
    pay_id = _next_id(view, "payees", "pay")
    rec = {
        "id": pay_id,
        "account_id": args["account_id"],
        "name": args["name"],
        "account_ref": args["account_ref"],
    }
    return ToolOutcome(
        result={"payee_id": pay_id, "name": rec["name"]},
        patch=[PatchOp(op="add", collection="payees", id=pay_id, value=rec)],
    )


def get_kyc_status(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    cust: Any = view.get("customers", str(args["customer_id"]))
    if cust is None:
        return _err("not_found")
    keep = ("id", "kyc_status", "last_review", "documents_missing", "tax_id")
    return ToolOutcome(result={k: cust[k] for k in keep})
