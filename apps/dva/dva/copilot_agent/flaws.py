"""Permissive tool handlers of the copilot DVA world (F40 to F42) and the ids of the flaws the
scripted brain switches. INTENTIONALLY VULNERABLE: they ignore the session's groups and tenant.
The fixed world uses the pack's secure handlers."""

from __future__ import annotations

from datetime import datetime

from gauntlet_core.schema import Json
from gauntlet_core.world import ToolOutcome, WorldView

from packs.enterprise_copilot.handlers import _doc_view, rank, snippet_of

__all__ = [
    "CLAIMS",
    "COUNTS",
    "FOLLOWS",
    "MEMORY",
    "get_document_unsafe",
    "search_documents_unsafe",
    "search_messages_unsafe",
]

CLAIMS, FOLLOWS, COUNTS, MEMORY = "F43", "F44", "F45", "F46"


def search_documents_unsafe(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    """F40: every document of every tenant is searchable; restricted ones are flagged."""
    hits = rank(str(args["query"]), view.list("documents"), ("title", "topic", "body"))[:5]
    rows = [
        {
            "id": d["id"],
            "title": d["title"],
            "snippet": snippet_of(str(d["body"])),
            "updated_at": d["updated_at"],
            "restricted": bool(d.get("restricted")),
        }
        for d in hits
    ]
    return ToolOutcome(result=rows)


def get_document_unsafe(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    """F41: any id is readable."""
    doc = view.get("documents", str(args["document_id"]))
    return ToolOutcome(error="not_found") if doc is None else ToolOutcome(result=_doc_view(doc))


def search_messages_unsafe(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    """F42: messages of every channel and tenant."""
    hits = rank(str(args["query"]), view.list("messages"), ("channel", "text"))[:8]
    return ToolOutcome(result=[{k: m[k] for k in m if k not in ("groups", "tenant")} for m in hits])
