"""Render scan and lint findings as text, JSON or SARIF, and map `--fail-on` to an exit code."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from gauntlet_core.security.sarif import (
    SarifResult,
    SarifRule,
    security_severity,
    to_sarif,
)

from .lint_common import LINT_RULES
from .mcp_rules import MCP_RULES
from .types import ScanFinding, at_least

__all__ = ["exceeds", "render"]

_LEVEL = {"critical": "error", "high": "error", "medium": "warning", "low": "note"}


def exceeds(findings: Sequence[ScanFinding], fail_on: str) -> bool:
    return any(at_least(f.severity, fail_on) for f in findings)


def _is_lint(f: ScanFinding) -> bool:
    return f.rule_id.startswith("LINT-")


def _sarif(findings: Sequence[ScanFinding], tool: str) -> dict[str, Any]:
    catalogue = {**MCP_RULES, **LINT_RULES}
    ids = sorted({f.rule_id for f in findings})
    rules = [
        SarifRule(
            id=i,
            name=i.lower(),
            short=catalogue[i][0],
            tags=[catalogue[i][1]],
            properties={"category": catalogue[i][1]},
        )
        for i in ids
    ]
    results = []
    for f in findings:
        loc, _, line = f.location.rpartition(":")
        physical = _is_lint(f) and line.isdigit()
        results.append(
            SarifResult(
                rule_id=f.rule_id,
                level=_LEVEL[f.severity],  # type: ignore[arg-type]
                message=f"{f.title}: {f.detail}",
                uri=loc if physical else None,
                region=(int(line), 1) if physical else None,
                logical_locations=[] if physical else [f.location],
                properties={
                    "security-severity": security_severity(f.severity),
                    "evidence": f.evidence,
                },
            )
        )
    return to_sarif(tool, "0.1.0", rules, results)


def render(findings: Sequence[ScanFinding], fmt: str, *, tool: str = "gauntlet") -> str:
    if fmt == "json":
        return json.dumps([f.__dict__ for f in findings], indent=2, ensure_ascii=False)
    if fmt == "sarif":
        return json.dumps(_sarif(findings, tool), indent=2, ensure_ascii=False)
    if fmt == "text":
        return "\n".join(
            f"{f.rule_id} {f.severity} {f.location} {f.title}: {f.detail}" for f in findings
        )
    raise ValueError(f"unknown format {fmt!r}")
