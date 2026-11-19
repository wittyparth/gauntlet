"""SARIF 2.1.0 writer and a structural validator.

The official JSON schema is published by OASIS in `oasis-tcs/sarif-spec`, whose licence is not
machine-identifiable (GitHub reports NOASSERTION), so the schema is not vendored. `validate_sarif`
checks the parts of the 2.1.0 structure this writer produces instead.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

__all__ = [
    "SARIF_SCHEMA_URI",
    "SarifResult",
    "SarifRule",
    "security_severity",
    "to_sarif",
    "validate_sarif",
]

SARIF_SCHEMA_URI = "https://json.schemastore.org/sarif-2.1.0.json"
INFORMATION_URI = "https://github.com/gauntlet"
Level = Literal["error", "warning", "note"]
LEVELS = ("error", "warning", "note", "none")
_SEVERITY = {"critical": "9.5", "high": "8.0", "medium": "5.0", "low": "2.0"}


def security_severity(severity: str) -> str:
    """GitHub code-scanning `security-severity` string for a Gauntlet severity."""
    return _SEVERITY[severity]


@dataclass(frozen=True)
class SarifRule:
    id: str
    name: str
    short: str
    full: str = ""
    help_uri: str | None = None
    default_level: Level = "warning"
    tags: Sequence[str] = ()
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SarifResult:
    rule_id: str
    level: Level
    message: str
    logical_locations: Sequence[str] = ()
    uri: str | None = None
    region: tuple[int, int] | None = None
    fingerprint: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)


def _rule(r: SarifRule) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": r.id,
        "name": r.name,
        "shortDescription": {"text": r.short},
        "defaultConfiguration": {"level": r.default_level},
    }
    if r.full:
        out["fullDescription"] = {"text": r.full}
    if r.help_uri:
        out["helpUri"] = r.help_uri
    props = dict(r.properties)
    if r.tags:
        props["tags"] = list(r.tags)
    if props:
        out["properties"] = props
    return out


def _result(r: SarifResult, index: int) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ruleId": r.rule_id,
        "ruleIndex": index,
        "level": r.level,
        "message": {"text": r.message},
    }
    loc: dict[str, Any] = {}
    if r.uri is not None:
        phys: dict[str, Any] = {"artifactLocation": {"uri": r.uri}}
        if r.region is not None:
            phys["region"] = {"startLine": r.region[0], "startColumn": r.region[1]}
        loc["physicalLocation"] = phys
    if r.logical_locations:
        loc["logicalLocations"] = [{"name": n, "kind": "function"} for n in r.logical_locations]
    if loc:
        out["locations"] = [loc]
    if r.fingerprint:
        out["partialFingerprints"] = {"gauntlet/v1": r.fingerprint}
    if r.properties:
        out["properties"] = dict(r.properties)
    return out


def to_sarif(
    tool_name: str,
    tool_version: str,
    rules: Sequence[SarifRule],
    results: Sequence[SarifResult],
) -> dict[str, Any]:
    index = {r.id: i for i, r in enumerate(rules)}
    return {
        "$schema": SARIF_SCHEMA_URI,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": tool_name,
                        "version": tool_version,
                        "informationUri": INFORMATION_URI,
                        "rules": [_rule(r) for r in rules],
                    }
                },
                "results": [_result(r, index[r.rule_id]) for r in results],
            }
        ],
    }


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v)


def validate_sarif(doc: Any) -> list[str]:
    """Structural problems in a SARIF 2.1.0 document (empty list means valid)."""
    out: list[str] = []
    if not isinstance(doc, dict):
        return ["document is not an object"]
    if doc.get("version") != "2.1.0":
        out.append("version must be '2.1.0'")
    runs = doc.get("runs")
    if not isinstance(runs, list) or not runs:
        return [*out, "runs must be a non-empty array"]
    for ri, run in enumerate(runs):
        driver = (run.get("tool") or {}).get("driver") if isinstance(run, dict) else None
        if not isinstance(driver, dict) or not _is_str(driver.get("name")):
            out.append(f"runs[{ri}].tool.driver.name is required")
            continue
        rules = driver.get("rules", [])
        ids = [r.get("id") for r in rules]
        if len(set(ids)) != len(ids):
            out.append(f"runs[{ri}]: duplicate rule ids")
        for i, res in enumerate(run.get("results", [])):
            where = f"runs[{ri}].results[{i}]"
            if not _is_str((res.get("message") or {}).get("text")):
                out.append(f"{where}.message.text is required")
            if res.get("level", "warning") not in LEVELS:
                out.append(f"{where}.level {res.get('level')!r} is invalid")
            idx = res.get("ruleIndex")
            if idx is not None and not (
                isinstance(idx, int) and 0 <= idx < len(rules) and ids[idx] == res.get("ruleId")
            ):
                out.append(f"{where}.ruleIndex does not match ruleId")
            for loc in res.get("locations", []):
                phys = loc.get("physicalLocation")
                if phys is not None and not _is_str(
                    (phys.get("artifactLocation") or {}).get("uri")
                ):
                    out.append(f"{where}: physicalLocation needs artifactLocation.uri")
                if phys is None and not loc.get("logicalLocations"):
                    out.append(f"{where}: location has neither physical nor logical part")
    return out
