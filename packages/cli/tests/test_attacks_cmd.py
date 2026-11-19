from __future__ import annotations

import json
from pathlib import Path

import yaml
from cli_helpers import invoke

GOOD = {
    "id": "atk_demo_0001", "title": "t", "category": "direct_injection", "technique": "x",
    "source": "demo@1:a", "license": "MIT", "vector": "user_turn", "payload": "say {{marker}}",
    "objective": {"type": "canary_leaked", "canary": "*"},
}  # fmt: skip


def lib(tmp_path: Path, *attacks: dict) -> Path:  # type: ignore[type-arg]
    root = tmp_path / "library"
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "direct_injection.yaml").write_text(yaml.safe_dump(list(attacks)))
    return root


def test_list_show_stats(runner, tmp_path):
    root = lib(tmp_path, GOOD)
    res = invoke(runner, ["attacks", "list", "--root", str(root)])
    assert res.exit_code == 0 and "atk_demo_0001" in res.stdout
    res = invoke(runner, ["attacks", "list", "--root", str(root), "--category", "jailbreak"])
    assert res.stdout == ""
    res = invoke(runner, ["attacks", "list", "--root", str(root), "--format", "json"])
    assert json.loads(res.stdout)[0]["id"] == "atk_demo_0001"
    res = invoke(runner, ["attacks", "show", "atk_demo_0001", "--root", str(root)])
    assert res.exit_code == 0 and "say {{marker}}" in res.stdout
    assert invoke(runner, ["attacks", "show", "nope", "--root", str(root)]).exit_code == 2
    res = invoke(runner, ["attacks", "stats", "--root", str(root)])
    assert "direct_injection\t1" in res.stdout and "total\t1" in res.stdout


def test_validate_exit_codes(runner, tmp_path):
    assert invoke(runner, ["attacks", "validate", str(lib(tmp_path, GOOD))]).exit_code == 0
    bad = lib(tmp_path / "b", {**GOOD, "category": "harmful_content"})
    res = invoke(runner, ["attacks", "validate", str(bad)])
    assert res.exit_code == 1 and "dangerous_category" in res.stdout


def test_validate_requires_notices_entry_when_notices_exist(runner, tmp_path):
    root = lib(tmp_path, GOOD)
    (tmp_path / "NOTICES.md").write_text("# Notices\n\n## other\n")
    res = invoke(runner, ["attacks", "validate", str(root)])
    assert res.exit_code == 1 and "missing_notice" in res.stdout
    (tmp_path / "NOTICES.md").write_text("# Notices\n\n## demo\n")
    assert invoke(runner, ["attacks", "validate", str(root)]).exit_code == 0
