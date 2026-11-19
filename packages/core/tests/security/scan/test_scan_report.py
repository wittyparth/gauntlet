import json
from pathlib import Path

from gauntlet_core.security.sarif import validate_sarif
from gauntlet_core.security.scan import (
    ScanFinding,
    exceeds,
    lint_paths,
    render,
    scan_mcp_tools,
)

FIX = Path(__file__).resolve().parents[2] / "fixtures"


def f(sev: str, rule: str = "MCP-001", loc: str = "tool_a") -> ScanFinding:
    return ScanFinding(rule, sev, "Title", "detail", loc, "evidence", "mcp")  # type: ignore[arg-type]


def test_text_golden():
    out = render([f("high"), f("low", "MCP-006", "tool_b")], "text")
    assert out == ("MCP-001 high tool_a Title: detail\nMCP-006 low tool_b Title: detail")


def test_json_shape():
    [row] = json.loads(render([f("high")], "json"))
    assert set(row) == {
        "rule_id",
        "severity",
        "title",
        "detail",
        "location",
        "evidence",
        "category",
    }


def test_sarif_for_mcp_uses_logical_locations_only():
    findings = scan_mcp_tools(json.loads((FIX / "mcp" / "poisoned.json").read_text()))
    doc = json.loads(render(findings, "sarif"))
    assert validate_sarif(doc) == []
    loc = doc["runs"][0]["results"][0]["locations"][0]
    assert "physicalLocation" not in loc and loc["logicalLocations"][0]["name"]


def test_sarif_for_lint_has_physical_locations_and_severity():
    findings = lint_paths([FIX / "lint" / "bad_agent.py"])
    doc = json.loads(render(findings, "sarif"))
    assert validate_sarif(doc) == []
    results = doc["runs"][0]["results"]
    assert all("physicalLocation" in r["locations"][0] for r in results)
    assert {r["properties"]["security-severity"] for r in results} <= {"9.5", "8.0", "5.0", "2.0"}
    assert len({r["ruleId"] for r in results}) >= 6


def test_fail_on_threshold_mapping():
    findings = [f("low"), f("medium")]
    assert exceeds(findings, "low") and exceeds(findings, "medium")
    assert not exceeds(findings, "high") and not exceeds(findings, "critical")
    assert exceeds([*findings, f("critical")], "critical")
    assert not exceeds([], "low")
