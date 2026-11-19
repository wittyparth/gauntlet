import pytest
from gauntlet_core.security.sarif import (
    SarifResult,
    SarifRule,
    security_severity,
    to_sarif,
    validate_sarif,
)

RULES = [SarifRule(id="MCP-001", name="hidden-instructions", short="Hidden instructions")]


def test_document_is_structurally_valid():
    doc = to_sarif(
        "gauntlet",
        "0.1.0",
        RULES,
        [
            SarifResult(
                rule_id="MCP-001",
                level="error",
                message="m",
                uri="a.py",
                region=(3, 1),
                fingerprint="abc",
            )
        ],
    )
    assert doc["version"] == "2.1.0" and "$schema" in doc
    assert validate_sarif(doc) == []
    res = doc["runs"][0]["results"][0]
    assert res["ruleIndex"] == 0
    loc = res["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uri"] == "a.py"
    assert loc["region"] == {"startLine": 3, "startColumn": 1}
    assert res["partialFingerprints"] == {"gauntlet/v1": "abc"}


def test_logical_location_only_result_is_valid():
    doc = to_sarif(
        "g", "1", RULES, [SarifResult("MCP-001", "warning", "m", logical_locations=["tool_x"])]
    )
    assert validate_sarif(doc) == []
    loc = doc["runs"][0]["results"][0]["locations"][0]
    assert "physicalLocation" not in loc
    assert loc["logicalLocations"] == [{"name": "tool_x", "kind": "function"}]


def test_empty_results_is_valid():
    assert validate_sarif(to_sarif("g", "1", RULES, [])) == []


def test_severity_mapping():
    assert [security_severity(s) for s in ("critical", "high", "medium", "low")] == [
        "9.5",
        "8.0",
        "5.0",
        "2.0",
    ]


def test_validator_flags_problems():
    doc = to_sarif("g", "1", RULES, [SarifResult("MCP-001", "note", "m")])
    doc["runs"][0]["results"][0]["ruleIndex"] = 5
    doc["runs"][0]["results"][0]["level"] = "fatal"
    doc["version"] = "2.0.0"
    issues = validate_sarif(doc)
    assert len(issues) >= 3


def test_unknown_rule_id_raises():
    with pytest.raises(KeyError):
        to_sarif("g", "1", RULES, [SarifResult("NOPE", "note", "m")])
