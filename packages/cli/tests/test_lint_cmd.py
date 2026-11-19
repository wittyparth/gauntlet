from __future__ import annotations

import json
from pathlib import Path

from cli_helpers import invoke

LINT = Path(__file__).resolve().parents[2] / "core" / "tests" / "fixtures" / "lint"


def test_bad_fixture_exits_1_and_good_exits_0(runner):
    res = invoke(runner, ["lint", str(LINT / "bad_agent.py")])
    assert res.exit_code == 1 and "LINT-001" in res.stdout
    assert invoke(runner, ["lint", str(LINT / "good_agent.py")]).exit_code == 0
    assert invoke(runner, ["lint", str(LINT / "good_config.yaml")]).exit_code == 0


def test_sarif_output_is_valid_with_six_plus_rules(runner):
    res = invoke(runner, ["lint", str(LINT / "bad_agent.py"), "--format", "sarif"])
    doc = json.loads(res.stdout)
    assert doc["version"] == "2.1.0"
    assert len({r["ruleId"] for r in doc["runs"][0]["results"]}) >= 6


def test_fail_on_select_ignore_and_directory(runner):
    bad = str(LINT / "bad_agent.py")
    assert invoke(runner, ["lint", bad, "--fail-on", "critical"]).exit_code == 0
    res = invoke(runner, ["lint", bad, "--select", "LINT-004", "--fail-on", "medium"])
    assert res.exit_code == 1 and {ln.split()[0] for ln in res.stdout.splitlines()} == {"LINT-004"}
    res = invoke(runner, ["lint", bad, "--ignore", "LINT-001,LINT-002,LINT-005,LINT-010,LINT-011"])
    assert "LINT-001" not in res.stdout
    assert invoke(runner, ["lint", str(LINT)]).exit_code == 1


def test_usage_errors_exit_2(runner):
    assert invoke(runner, ["lint", "/no/such/path"]).exit_code == 2
    assert invoke(runner, ["lint", str(LINT), "--fail-on", "nope"]).exit_code == 2
