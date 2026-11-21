from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "checks"))

from check_helpers import Tb
from gauntlet_core.policy.blast import blast_radius, observe, permission_diff
from gauntlet_core.schema import PatchOp, Policy, ToolSpec


def tool(name: str, risk: str, props: dict | None = None, **kw: Any) -> ToolSpec:
    handler = kw.pop("handler", {"kind": "static", "result": {}})
    return ToolSpec.model_validate(
        {
            "name": name,
            "description": name,
            "risk": risk,
            "handler": handler,
            "input_schema": {"type": "object", "properties": props or {}, **kw.pop("schema", {})},
            **kw,
        }
    )


def policy(*rules: dict) -> Policy:
    return Policy.model_validate({"id": "p", "rules": list(rules)})


def rule(rid: str, tool_name: str, action: str = "block") -> dict:
    return {
        "id": rid,
        "description": rid,
        "when": {"type": "tool_called", "tool": tool_name},
        "action": action,
    }


TOOLS = [
    tool("lookup", "read"),
    tool("update_address", "write"),
    tool("issue_refund", "financial"),
    tool("send_email", "external_comm"),
    tool("delete_order", "destructive"),
]


def test_exposure_scores_and_coverage():
    none = blast_radius(TOOLS, observe([]), None)
    assert none.exposure_score == none.exposure_score_without_policy == 0 + 1 + 3 + 2 + 3
    pol = policy(rule("r1", "issue_refund"), rule("r2", "send_email", "require_approval"))
    br = blast_radius(TOOLS, observe([]), pol)
    assert br.exposure_score == 1 + 3 and br.exposure_score_without_policy == 9
    by = {t.tool: t for t in br.tools}
    assert (
        by["issue_refund"].covered_by_rules == ["r1"] and not by["issue_refund"].approval_required
    )
    assert by["send_email"].approval_required and by["lookup"].covered_by_rules == []


def test_log_rules_do_not_cover_and_wildcard_covers_everything():
    br = blast_radius(TOOLS, observe([]), policy(rule("l", "issue_refund", "log")))
    assert br.exposure_score == 9
    assert blast_radius(TOOLS, observe([]), policy(rule("all", "*"))).exposure_score == 0


def test_untrusted_output_tools_double_the_score():
    tools = [*TOOLS, tool("fetch_page", "read", untrusted_output=True)]
    br = blast_radius(tools, observe([]), None)
    assert br.exposure_score == 18 and br.untrusted_output_tools == ["fetch_page"]


def test_collections_and_observed_effects():
    crud = tool(
        "create_refund",
        "financial",
        handler={"kind": "crud", "collection": "refunds", "op": "create"},
    )
    reader = tool(
        "get_order", "read", handler={"kind": "crud", "collection": "orders", "op": "get"}
    )
    tb = Tb()
    tb.call("create_refund", {"order_id": "o1"}, patch=[
        PatchOp(op="add", collection="refunds", id="r1", value={"id": "r1"}),
        PatchOp(op="replace", collection="orders", id="o1", value={"id": "o1"},
                before={"id": "o1"}),
    ])  # fmt: skip
    tb.call("create_refund", {"order_id": "o2"})
    tb.call("get_order", {"order_id": "o1"})
    obs = observe([tb.build()])
    br = blast_radius([crud, reader], obs, None)
    by = {t.tool: t for t in br.tools}
    assert by["create_refund"].collections_written == ["orders", "refunds"]
    assert by["create_refund"].max_records_changed_per_call == 2
    assert by["create_refund"].calls_observed == 2 and by["get_order"].calls_observed == 1
    assert by["get_order"].collections_written == []
    assert "can move money" in by["create_refund"].worst_case
    assert "up to 2 record(s) per call" in by["create_refund"].worst_case


# -- permission diff ----------------------------------------------------------------------


def test_new_financial_tool_without_a_rule_is_newly_uncovered():
    old = [tool("lookup", "read")]
    new = [tool("lookup", "read"), tool("issue_refund", "financial")]
    d = permission_diff(old, new, None)
    assert d.added_tools == ["issue_refund"] and d.removed_tools == []
    assert d.newly_uncovered == ["issue_refund"] and d.exposure_score_delta == 3
    covered = permission_diff(old, new, policy(rule("r", "issue_refund")))
    assert covered.newly_uncovered == [] and covered.exposure_score_delta == 0


def test_risk_upgrade_and_removal():
    old = [tool("a", "read"), tool("b", "financial"), tool("c", "write")]
    new = [tool("a", "destructive"), tool("c", "write")]
    d = permission_diff(old, new, None)
    assert [(c.tool, c.old, c.new) for c in d.risk_changes] == [("a", "read", "destructive")]
    assert d.removed_tools == ["b"] and d.newly_uncovered == ["a"]
    down = permission_diff(new, old, None)  # a downgrade is not a risk change
    assert down.risk_changes == [] and down.added_tools == ["b"]


def test_schema_widenings():
    old = [
        tool(
            "t",
            "write",
            {
                "id": {"type": "string"},
                "n": {"type": "integer"},
                "mode": {"type": "string", "enum": ["a", "b"]},
                "locked": {"type": "string", "enum": ["x"]},
            },
            schema={"required": ["id", "n"]},
        )
    ]
    new = [
        tool(
            "t",
            "write",
            {
                "id": {"type": ["string", "null"]},
                "n": {"type": "number"},
                "mode": {"type": "string", "enum": ["a", "b", "c"]},
                "locked": {"type": "string"},
                "extra": {"type": "string"},
            },
            schema={"required": ["id"]},
        )
    ]
    d = permission_diff(old, new, None)
    got = {(w.path, w.change) for w in d.schema_widenings}
    assert ("id", "type widened from ['string'] to ['null', 'string']") in got
    assert ("n", "type widened from ['integer'] to ['number']") in got
    assert ("mode", "enum values added: ['c']") in got
    assert ("locked", "enum constraint removed") in got
    assert ("extra", "property added") in got and ("n", "no longer required") in got
    assert ("id", "no longer required") not in got
    assert permission_diff(old, old, None).schema_widenings == []


def test_newly_uncovered_when_coverage_drops_by_upgrade():
    pol = policy(rule("r", "b"))
    old, new = [tool("a", "read"), tool("b", "write")], [tool("a", "financial"), tool("b", "write")]
    d = permission_diff(old, new, pol)
    assert d.newly_uncovered == ["a"] and d.exposure_score_delta == 3
