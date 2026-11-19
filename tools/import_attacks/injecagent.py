"""InjecAgent importer: reads `data/attacker_cases_*.jsonl` from a checkout."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .common import Candidate, Skip, load_mapping

SOURCE = "injecagent"
_CAMEL_TOOL = re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+){2,}\b")


def _substitute(text: str, subs: list[dict[str, str]]) -> str:
    for s in subs:
        text = re.sub(s["pattern"], s["value"], text)
    return text


def read_candidates(src: Path) -> tuple[list[Candidate], list[Skip]]:
    m = load_mapping(SOURCE)
    cands: list[Candidate] = []
    skips: list[Skip] = []
    for kind, rel in m["files"].items():
        rows = [json.loads(line) for line in (src / rel).read_text().splitlines() if line.strip()]
        for i, row in enumerate(rows):
            uid = f"{kind}:{i}"
            if row.get("Attack Type") in m["exclude_types"]:
                skips.append(Skip(SOURCE, uid, "excluded_type", str(row.get("Attack Type"))))
                continue
            text = str(row["Attacker Instruction"])
            tools: list[str] = row.get("Attacker Tools") or []
            if any(t in text for t in tools) or _CAMEL_TOOL.search(text):
                skips.append(Skip(SOURCE, uid, "upstream_tool_name", "names an upstream tool"))
                continue
            cands.append(_candidate(kind, uid, row, _substitute(text, m["substitutions"])))
    return cands, skips


def _candidate(kind: str, uid: str, row: dict[str, Any], text: str) -> Candidate:
    attack_type = str(row.get("Attack Type", ""))
    if kind == "direct_harm":
        return Candidate(
            upstream_id=uid,
            title=f"InjecAgent direct harm ({attack_type})",
            category="indirect_injection",
            vector="tool_result",
            technique="tool-result injection: direct harm; objective_source: substituted",
            payload=text,
            objective={
                "type": "tainted_call",
                "tool": "*",
                "risk": ["write", "destructive", "financial"],
            },
            requires=["untrusted_tool_output"],
            group=kind,
        )
    return Candidate(
        upstream_id=uid,
        title=f"InjecAgent data stealing ({attack_type})",
        category="exfiltration",
        vector="tool_result",
        technique="tool-result injection: data stealing; objective_source: substituted",
        payload=text,
        objective={
            "type": "any",
            "of": [
                {"type": "tainted_call", "tool": "*", "risk": ["external_comm"]},
                {"type": "egress", "allow_domains": [], "allow_recipients": []},
            ],
        },
        requires=["untrusted_tool_output", "tool:external_comm"],
        group=kind,
    )
