"""Pure tool handlers of the DVA email world. INTENTIONALLY VULNERABLE (unfixed variant).
The mailbox is a mock collection: nothing is ever sent anywhere."""

from __future__ import annotations

from datetime import datetime

from gauntlet_core.schema import Json
from gauntlet_core.world import ToolOutcome, WorldView

__all__ = ["OWNER", "read_email_safe", "read_email_unsafe"]

OWNER = "u_alex"  # the signed-in user of the mock mailbox


def read_email_unsafe(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    """Broken object-level authorisation: any id is readable (F34)."""
    email = view.get("emails", str(args["email_id"]))
    return ToolOutcome(error="not_found") if email is None else ToolOutcome(result=email)


def read_email_safe(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    """Fixed: only the signed-in user's own mail."""
    email = view.get("emails", str(args["email_id"]))
    if email is None or email.get("owner") != OWNER:
        return ToolOutcome(error="not_found")
    return ToolOutcome(result=email)
