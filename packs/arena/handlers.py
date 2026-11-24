"""Pure tool handlers of the arena world. A stored note carries a taint marker derived from its
text, so the gateway's taint rules can follow it into later tool calls (level 4)."""

from __future__ import annotations

import hashlib
from datetime import datetime

from gauntlet_core.schema import Json, PatchOp
from gauntlet_core.world import ToolOutcome, WorldView

MAX_NOTE = 400


def add_order_note(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    order = view.get("orders", str(args["order_id"]))
    if order is None:
        return ToolOutcome(error="not_found")
    note = str(args["note"])[:MAX_NOTE]
    marker = "gmk-" + hashlib.sha256(note.encode()).hexdigest()[:12]
    new = {**order, "notes": [*order.get("notes", []), f"{note} [{marker}]"]}
    return ToolOutcome(
        result={"order_id": order["id"], "notes": len(new["notes"])},
        patch=[PatchOp(op="replace", collection="orders", id=order["id"], value=new, before=order)],
    )
