"""The decision record the gateway emits for every checked action (P4-2)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from gauntlet_core.engine.redact import redact
from gauntlet_core.schema import Evidence, Json, Model, Severity

__all__ = [
    "ARG_LOG_LIMIT",
    "ApprovalInfo",
    "DecisionRecord",
    "LogArgs",
    "render_args",
    "render_evidence",
]

ARG_LOG_LIMIT = 2048
LogArgs = Literal["full", "redacted", "hash"]
RecordAction = Literal["allow", "block", "require_approval", "redact", "log"]


class ApprovalInfo(Model):
    id: str
    outcome: Literal["pending", "approved", "denied", "expired"] = "pending"


class DecisionRecord(Model):
    id: str
    ts: datetime
    session_id: str
    agent_id: str | None = None
    policy_id: str
    policy_version: int
    mode: Literal["shadow", "enforce"]
    kind: Literal["tool_call", "output"]
    tool: str | None = None
    args: Json | None = None  # per `log_args`
    action: RecordAction  # what actually happened
    enforced: bool  # False in shadow mode
    would_have: RecordAction | None = None  # shadow mode: what enforce would have done
    rule_id: str | None = None
    severity: Severity | None = None
    message: str | None = None
    evidence: list[Evidence] = []
    approval: ApprovalInfo | None = None
    overhead_us: int = 0
    guard_error: str | None = None


def _canonical(args: Any) -> str:
    return json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def render_args(args: Json, mode: LogArgs) -> Json:
    """How arguments are stored. `redacted` removes secrets and truncates to 2 KB, `hash`
    keeps only a sha256, `full` stores what the agent sent (unsafe for secrets)."""
    if mode == "full":
        return args
    if mode == "hash":
        return {"sha256": hashlib.sha256(_canonical(args).encode()).hexdigest()}
    clean = redact(args)
    text = _canonical(clean)
    if len(text) <= ARG_LOG_LIMIT:
        return clean  # type: ignore[no-any-return]
    return {"_truncated": text[:ARG_LOG_LIMIT]}


def render_evidence(evidence: list[Evidence], mode: LogArgs) -> list[Evidence]:
    """Evidence quotes can contain arguments, so they follow the same rule."""
    if mode == "full":
        return evidence
    return [
        e.model_copy(
            update={"quote": None if mode == "hash" else redact(e.quote)[:ARG_LOG_LIMIT]}
            if e.quote
            else {}
        )
        for e in evidence
    ]
