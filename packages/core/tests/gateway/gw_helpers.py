"""Shared builders for the gateway tests."""

from __future__ import annotations

from typing import Any

from gauntlet_core.schema import Check, Policy, PolicyRule
from pydantic import TypeAdapter

_CHECK = TypeAdapter(Check)


def rule(rid: str, when: dict[str, Any], **kw: Any) -> PolicyRule:
    return PolicyRule(id=rid, description=rid, when=_CHECK.validate_python(when), **kw)


def policy(*rules: PolicyRule, mode: str = "enforce", fail: str = "open") -> Policy:
    return Policy.model_validate(
        {"id": "pol_t", "version": 3, "rules": list(rules), "mode": mode, "fail": fail}
    )


def tool(name: str, **extra: Any) -> dict[str, Any]:
    return {"type": "tool_called", "tool": name, **extra}


REFUND_CAP = rule(
    "refund-cap",
    tool("issue_refund", args={"amount_cents": {"gt": 10000}}),
    action="block",
    severity="critical",
    message="Refunds over 10000 cents are not allowed.",
)
