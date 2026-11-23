"""Pure tool handlers of the enterprise copilot world. The acting user is world state
(`session/current`, CQ-P1): these secure handlers filter every read by that record's groups and
tenant, so an answer can never contain what the user may not see. `search_documents` ranks by
word overlap and is deterministic."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from gauntlet_core.schema import Json
from gauntlet_core.world import ToolOutcome, WorldView

__all__ = [
    "can_read",
    "get_document",
    "list_my_groups",
    "rank",
    "search_documents",
    "search_messages",
    "snippet_of",
]

_STOP = frozenset(
    [
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "what",
        "which",
        "about",
        "have",
        "has",
        "you",
        "your",
        "our",
        "are",
        "was",
        "were",
        "can",
        "could",
        "please",
        "show",
        "tell",
        "give",
        "find",
        "any",
        "all",
        "how",
        "many",
        "who",
        "where",
        "when",
        "why",
        "does",
        "did",
        "not",
        "but",
        "into",
        "over",
        "under",
        "document",
        "documents",
        "file",
        "files",
    ]
)


def _session(view: WorldView) -> dict[str, Any]:
    return view.get("session", "current") or {"groups": [], "tenant": ""}


def can_read(session: dict[str, Any], record: dict[str, Any]) -> bool:
    """Same tenant and at least one shared group. A former employee has no groups."""
    if record.get("tenant") != session.get("tenant"):
        return False
    return bool(set(record.get("groups", [])) & set(session.get("groups", [])))


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) >= 3 and w not in _STOP}


def rank(
    query: str, records: list[dict[str, Any]], fields: tuple[str, ...]
) -> list[dict[str, Any]]:
    want = _tokens(query)
    scored = []
    for r in records:
        have = _tokens(" ".join(str(r.get(f, "")) for f in fields))
        hits = len(want & have)
        if hits:
            scored.append((-hits, str(r["id"]), r))
    return [r for _, _, r in sorted(scored, key=lambda t: (t[0], t[1]))]


def snippet_of(text: str, n: int = 140) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def _doc_view(d: dict[str, Any]) -> dict[str, Any]:
    out = {k: d[k] for k in ("id", "title", "body", "updated_at") if k in d}
    for k in ("access_code", "stale", "superseded_by"):
        if k in d:
            out[k] = d[k]
    return out


def search_documents(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    session = _session(view)
    docs = [d for d in view.list("documents") if can_read(session, d)]
    hits = rank(str(args["query"]), docs, ("title", "topic", "body"))[:5]
    rows = []
    for d in hits:
        row = {
            "id": d["id"],
            "title": d["title"],
            "snippet": snippet_of(str(d["body"])),
            "updated_at": d["updated_at"],
        }
        if d.get("superseded_by"):
            row["superseded_by"] = d["superseded_by"]
        rows.append(row)
    return ToolOutcome(result=rows)


def get_document(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    doc = view.get("documents", str(args["document_id"]))
    # a document the user may not read is indistinguishable from one that does not exist
    if doc is None or not can_read(_session(view), doc):
        return ToolOutcome(error="not_found")
    return ToolOutcome(result=_doc_view(doc))


def list_my_groups(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    s = _session(view)
    return ToolOutcome(result={"user_id": s.get("user_id"), "groups": list(s.get("groups", []))})


def search_messages(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    session = _session(view)
    msgs = [m for m in view.list("messages") if can_read(session, m)]
    hits = rank(str(args["query"]), msgs, ("channel", "text"))[:8]
    return ToolOutcome(result=[{k: m[k] for k in m if k not in ("groups", "tenant")} for m in hits])
