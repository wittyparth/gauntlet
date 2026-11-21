"""Shared builders for the policy compiler tests."""

from __future__ import annotations

from typing import Any

from gauntlet_core.schema import ToolSpec

TOOLS = [
    ToolSpec.model_validate(
        {
            "name": name,
            "description": name,
            "risk": risk,
            "handler": {"kind": "static", "result": {}},
            "input_schema": {"type": "object", "properties": {a: {"type": "string"} for a in args}},
        }
    )
    for name, risk, args in [
        ("lookup_order", "read", ["order_id"]),
        ("issue_refund", "financial", ["order_id", "amount_cents", "reason"]),
        ("apply_coupon", "financial", ["order_id", "code"]),
        ("update_address", "write", ["order_id", "address"]),
        ("send_email", "external_comm", ["to", "body"]),
    ]
]


def rule(rid: str, when: dict[str, Any], **kw: Any) -> dict[str, Any]:
    return {"id": rid, "description": rid, "when": when, **kw}


def machine(clause_id: str, r: dict[str, Any], confidence: float = 0.9) -> dict[str, Any]:
    return {
        "clause_id": clause_id,
        "klass": "machine",
        "rule": r,
        "confidence": confidence,
        "rationale": "r",
    }


def tool(name: str, **extra: Any) -> dict[str, Any]:
    return {"type": "tool_called", "tool": name, **extra}


def rubric(rid: str = "x") -> dict[str, Any]:
    return {
        "id": rid,
        "title": "t",
        "question": "q?",
        "pass_definition": "p",
        "fail_definition": "f",
    }


def model(clause_id: str, confidence: float = 0.9) -> dict[str, Any]:
    return {
        "clause_id": clause_id,
        "klass": "model",
        "rubric": rubric(),
        "confidence": confidence,
        "rationale": "r",
    }


def batch(*items: dict[str, Any]) -> dict[str, Any]:
    return {"items": list(items)}
