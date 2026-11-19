from __future__ import annotations

from pathlib import Path

from cli_helpers import invoke
from gauntlet_core.eval import RunReport


def test_report_rerenders_from_run_dir(runner, smoke_args, tmp_path: Path):
    assert invoke(runner, smoke_args).exit_code == 0
    run_dir = str(tmp_path / "run")
    text = invoke(runner, ["report", run_dir])
    assert text.exit_code == 0
    assert (
        "Pass rate: 50%" in text.stdout
        and "FAIL" in text.stdout
        and "scn_tiny_cancel" in text.stdout
    )
    assert "Pack: tinyshop" in text.stdout
    md = invoke(runner, ["report", run_dir, "--format", "md"])
    assert md.stdout.startswith("# Gauntlet run ") and "| scn_tiny_status" in md.stdout
    js = invoke(runner, ["report", run_dir, "--json"])
    assert RunReport.model_validate_json(js.stdout).pass_rate == 0.5


def test_report_by_run_id_from_default_location(runner, pack, tmp_path, monkeypatch, smoke_args):
    monkeypatch.chdir(tmp_path)
    args = [a for a in smoke_args if a != str(tmp_path / "run")]
    args = args[: args.index("--out")]
    res = invoke(runner, [*args, "--json"])
    assert res.exit_code == 0
    run_id = RunReport.model_validate_json(res.stdout).run_id
    assert (tmp_path / ".gauntlet" / "runs" / run_id / "report.json").is_file()
    assert invoke(runner, ["report", run_id, "--json"]).exit_code == 0


def test_report_unknown_run_exits_2(runner, tmp_path):
    assert invoke(runner, ["report", str(tmp_path / "nothing")]).exit_code == 2
