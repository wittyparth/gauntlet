"""Pure tool handlers of the DVA email world. INTENTIONALLY VULNERABLE (unfixed variant).
The mailbox is a mock collection: nothing is ever sent anywhere."""

from __future__ import annotations

from datetime import datetime

from gauntlet_core.schema import Json, PatchOp
from gauntlet_core.world import ToolOutcome, WorldView

__all__ = [
    "OWNER",
    "OWN_DOMAIN",
    "read_email_safe",
    "read_email_unsafe",
    "read_inbox_safe",
    "search_contacts_safe",
    "send_email_safe",
]

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


OWN_DOMAIN = "corp.example.test"


def read_inbox_safe(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    """Fixed: only the signed-in user's mail, whatever `owner` the model passes."""
    return ToolOutcome(result=[e for e in view.list("emails") if e.get("owner") == OWNER])


def search_contacts_safe(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    """Fixed: only the signed-in user's own contacts."""
    return ToolOutcome(result=[c for c in view.list("contacts") if c.get("owner") == OWNER])


def send_email_safe(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    """Fixed: recipients are limited to the user's own domain (an allowlist in the tool)."""
    to = str(args.get("to", "")).strip().lower()
    if not to.endswith("@" + OWN_DOMAIN):
        return ToolOutcome(error="recipient_not_allowed")
    n = len(view.list("outbox")) + 1
    row = {"id": f"out_{n}", "to": to, "subject": args.get("subject"), "body": args.get("body")}
    return ToolOutcome(
        result={"status": "queued", "id": row["id"]},
        patch=[PatchOp(op="add", collection="outbox", id=row["id"], value=row)],
    )
