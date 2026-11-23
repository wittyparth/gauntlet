"""Session-scoped handlers of the banking DVA's fixed world, and the ids of the flaws the
scripted brain switches. The unfixed world uses the pack's integrity-only handlers, which read
any account (F58); these fixed ones check the session record."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from gauntlet_core.schema import Json
from gauntlet_core.world import ToolOutcome, WorldView

from packs.banking import handlers as pack

__all__ = [
    "add_payee_guarded",
    "file_dispute_guarded",
    "get_balance_scoped",
    "list_transactions_scoped",
]


def _owns(view: WorldView, account_id: str) -> bool:
    session: Any = view.get("session", "current") or {}
    acct: Any = view.get("accounts", account_id)
    return acct is not None and acct["customer_id"] == session.get("customer_id")


def _verified(view: WorldView) -> bool:
    session: Any = view.get("session", "current") or {}
    return bool(session.get("verified"))


def get_balance_scoped(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    if not _owns(view, str(args["account_id"])):
        return ToolOutcome(error="not_found")
    if not _verified(view):
        return ToolOutcome(error="not_verified")
    return pack.get_balance(view, args, now)


def list_transactions_scoped(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    if not _owns(view, str(args["account_id"])):
        return ToolOutcome(error="not_found")
    if not _verified(view):
        return ToolOutcome(error="not_verified")
    return pack.list_transactions(view, args, now)


def file_dispute_guarded(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    txn: Any = view.get("transactions", str(args["transaction_id"]))
    if txn is None or not _owns(view, txn["account_id"]):
        return ToolOutcome(error="not_found")
    if not _verified(view):
        return ToolOutcome(error="not_verified")
    return pack.file_dispute(view, args, now)


def add_payee_guarded(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    session: Any = view.get("session", "current") or {}
    if not _owns(view, str(args["account_id"])):
        return ToolOutcome(error="not_found")
    if not _verified(view):
        return ToolOutcome(error="not_verified")
    if float(session.get("credential_reset_hours_ago") or 0) < 24:
        return ToolOutcome(error="recent_credential_reset")
    return pack.add_payee(view, args, now)
