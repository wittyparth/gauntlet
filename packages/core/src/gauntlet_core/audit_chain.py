"""The audit log's hash chain, shared by the server (which writes it) and by offline
verification of evidence packs (which only reads it)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

__all__ = ["GENESIS", "ChainResult", "row_hash", "verify_rows"]

GENESIS = "0" * 64


def row_hash(
    prev_hash: str,
    *,
    id: str,
    workspace_id: str,
    ts: datetime,
    actor: str,
    action: str,
    subject_type: str,
    subject_id: str,
    detail: dict[str, Any],
) -> str:
    body = json.dumps(
        [id, workspace_id, ts.astimezone(UTC).isoformat(), actor, action, subject_type,
         subject_id, detail],
        sort_keys=True, separators=(",", ":"),
    )  # fmt: skip
    return hashlib.sha256((prev_hash + body).encode()).hexdigest()


@dataclass(frozen=True)
class ChainResult:
    ok: bool
    checked: int
    first_bad_id: str | None = None


def verify_rows(rows: Iterable[Mapping[str, Any]], *, anchor: str | None = None) -> ChainResult:
    """Verify consecutive rows (dicts with the audit columns, `ts` an ISO string or datetime).
    `anchor` is the `prev_hash` the first row must carry; an excerpt that does not start at the
    genesis passes the hash of the row before it (or None to trust the first row's `prev_hash`)."""
    prev = anchor
    n = 0
    for r in rows:
        ts = r["ts"] if isinstance(r["ts"], datetime) else datetime.fromisoformat(r["ts"])
        if prev is None:
            prev = r["prev_hash"]
        want = row_hash(
            prev, id=r["id"], workspace_id=r["workspace_id"], ts=ts, actor=r["actor"],
            action=r["action"], subject_type=r["subject_type"], subject_id=r["subject_id"],
            detail=r["detail"],
        )  # fmt: skip
        if r["prev_hash"] != prev or r["hash"] != want:
            return ChainResult(False, n, r["id"])
        prev, n = r["hash"], n + 1
    return ChainResult(True, n)
