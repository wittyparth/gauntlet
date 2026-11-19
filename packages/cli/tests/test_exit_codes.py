from __future__ import annotations

from pathlib import Path

from cli_helpers import FIXTURES, invoke
from gauntlet_core.eval import RunReport


def test_bad_arguments_exit_2(runner, pack):
    assert invoke(runner, ["run"]).exit_code == 2
    assert invoke(runner, ["run", str(pack)]).exit_code == 2  # no --target
    args = ["run", str(pack), "--target", str(FIXTURES / "agent.yaml"), "--fail-under", "2"]
    assert invoke(runner, args).exit_code == 2
    assert invoke(runner, ["run", str(pack), "--target", "/nope/agent.yaml"]).exit_code == 2
    assert invoke(runner, ["run", "/nope", "--target", str(FIXTURES / "agent.yaml")]).exit_code == 2


def test_estimate_over_budget_exits_3_without_force_and_runs_with_it(runner, smoke_args, llm_calls):
    over = [*smoke_args, "--budget-usd", "0.002"]
    res = invoke(runner, over)
    assert res.exit_code == 3 and "exceeds the budget" in res.stderr
    assert llm_calls == []
    forced = invoke(runner, [*over, "--force", "--json"])
    assert forced.exit_code == 0, forced.stderr
    assert RunReport.model_validate_json(forced.stdout).counted == 2


def test_budget_exhaustion_mid_run_exits_3(runner, smoke_args, tmp_path: Path):
    res = invoke(runner, [*smoke_args, "--budget-usd", "0.000001", "--force", "--json"])
    assert res.exit_code == 3
    rep = RunReport.model_validate_json(res.stdout)
    assert rep.counted == 0 and rep.excluded == {"budget_exhausted": 2}
    assert rep.pass_rate is None


def test_missing_script_makes_platform_failure_exit_3(runner, pack, tmp_path: Path):
    empty = tmp_path / "empty.yaml"
    empty.write_text("roles: {}\n")
    args = ["run", str(pack), "--target", str(FIXTURES / "agent.yaml"), "--fake-llm", str(empty),
            "--out", str(tmp_path / "r"), "--json"]  # fmt: skip
    res = invoke(runner, args)
    assert res.exit_code == 3  # every episode ends simulator_error: nothing counted
    assert RunReport.model_validate_json(res.stdout).counted == 0
