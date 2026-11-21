from __future__ import annotations

import json
from pathlib import Path

import yaml
from cli_helpers import invoke

RULE = {
    "id": "refund-cap",
    "description": "Refunds over 10000 cents need approval",
    "when": {
        "type": "tool_called",
        "tool": "issue_refund",
        "args": {"amount_cents": {"gt": 10000}},
    },
    "action": "require_approval",
}
WORLD = {
    "id": "w",
    "clock_start": "2026-01-01T00:00:00Z",
    "tools": [
        {
            "name": "issue_refund",
            "description": "d",
            "risk": "financial",
            "handler": {"kind": "static", "result": {}},
            "input_schema": {"type": "object", "properties": {"amount_cents": {"type": "integer"}}},
        }
    ],
}


def fake_llm(path: Path) -> Path:
    script = {
        "roles": {
            "generator": [
                {
                    "match": "Clauses:",
                    "replies": [
                        {
                            "parsed": {
                                "items": [
                                    {
                                        "clause_id": "c01",
                                        "klass": "machine",
                                        "rule": RULE,
                                        "confidence": 0.9,
                                        "rationale": "cap",
                                    },
                                    {
                                        "clause_id": "c02",
                                        "klass": "human",
                                        "confidence": 0.3,
                                        "rationale": "person",
                                    },
                                ]
                            }
                        }
                    ],
                }
            ]
        }
    }
    path.write_text(yaml.safe_dump(script))
    return path


def test_compile_then_validate(runner, tmp_path):
    src = tmp_path / "policy.md"
    src.write_text("1. Refunds over 10000 cents need escalation.\n2. Ask a lawyer first.\n")
    tools = tmp_path / "world.yaml"
    tools.write_text(yaml.safe_dump(WORLD))
    out = tmp_path / "out.yaml"
    res = invoke(
        runner,
        ["policy", "compile", str(src), "-o", str(out), "--tools", str(tools),
         "--fake-llm", str(fake_llm(tmp_path / "llm.yaml"))],
    )  # fmt: skip
    assert res.exit_code == 0, res.output
    assert "2 clauses: 1 machine, 0 model, 1 human" in res.stdout
    assert "low confidence, review: c02" in res.stdout
    loaded = yaml.safe_load(out.read_text())
    assert [r["id"] for r in loaded["rules"]] == ["refund-cap"]
    assert loaded["rules"][0]["severity"] == "medium"  # keyword defaults applied
    proposals = json.loads((tmp_path / "out.yaml.proposals.json").read_text())
    assert [p["clause_id"] for p in proposals["proposals"]] == ["c01", "c02"]

    ok = invoke(runner, ["policy", "validate", str(out)])
    assert ok.exit_code == 0 and "ok (1 rules" in ok.stdout


def test_compile_agent_text_and_usage_errors(runner, tmp_path):
    llm = fake_llm(tmp_path / "llm.yaml")
    out = tmp_path / "o.yaml"
    res = invoke(
        runner,
        [
            "policy",
            "compile",
            "--agent-text",
            "1. a\n2. b\n",
            "-o",
            str(out),
            "--fake-llm",
            str(llm),
        ],
    )
    assert res.exit_code == 0 and out.exists()
    assert invoke(runner, ["policy", "compile"]).exit_code == 2
    both = invoke(runner, ["policy", "compile", str(out), "--agent-text", "x"])
    assert both.exit_code == 2
    assert invoke(runner, ["policy", "compile", str(tmp_path / "missing.md")]).exit_code == 2


def test_validate_reports_problems(runner, tmp_path):
    bad = {
        "id": "p",
        "rules": [
            {"id": "j", "description": "j", "when": {"type": "judge", "rubric": "x"}},
            {"id": "j", "description": "dup", "when": {"type": "tool_called", "tool": "t"}},
        ],
    }
    f = tmp_path / "bad.yaml"
    f.write_text(yaml.safe_dump(bad))
    res = invoke(runner, ["policy", "validate", str(f)])
    assert res.exit_code == 1 and "judge" in res.output and "duplicate" in res.output
    f.write_text("not: [valid")
    assert invoke(runner, ["policy", "validate", str(f)]).exit_code == 2
    assert invoke(runner, ["policy", "validate", str(tmp_path / "none.yaml")]).exit_code == 2
