"""`gauntlet gate`: exit codes 0, 1, 2, 3 on local run directories and against a server."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import respx
from cli_helpers import invoke
from gauntlet_core.eval.pr_comment import MARKER

API = "http://api.test"


def make_run(runner, smoke_args, *extra) -> Path:
    res = invoke(runner, [*smoke_args, *extra])
    assert res.exit_code in (0, 3), res.stderr
    return Path(smoke_args[-1])


def gates_file(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "gates.yaml"
    p.write_text(text)
    return p


def test_local_pass_exit_0_and_json_out(runner, smoke_args, tmp_path):
    run_dir = make_run(runner, smoke_args)
    out = tmp_path / "gate-result.json"
    res = invoke(runner, ["gate", "--run", str(run_dir), "--format", "json", "--out", str(out)])
    assert res.exit_code == 0, res.stderr
    assert json.loads(res.stdout)["status"] == "pass"
    assert json.loads(out.read_text())["passed"] is True


def test_local_failed_gate_exits_1(runner, smoke_args, tmp_path):
    run_dir = make_run(runner, smoke_args)
    g = gates_file(tmp_path, "gates:\n  pass_rate: {min: 1.5}\n")
    res = invoke(runner, ["gate", "--run", str(run_dir), "--gates", str(g)])
    assert res.exit_code == 1
    assert "FAIL" in res.stdout and "pass_rate" in res.stdout


def test_usage_errors_exit_2(runner, smoke_args, tmp_path):
    run_dir = make_run(runner, smoke_args)
    assert invoke(runner, ["gate"]).exit_code == 2
    assert invoke(runner, ["gate", "--run", str(run_dir), "--gates", "/nope.yaml"]).exit_code == 2
    bad = gates_file(tmp_path, "gates:\n  bogus: {}\n")
    res = invoke(runner, ["gate", "--run", str(run_dir), "--gates", str(bad)])
    assert res.exit_code == 2 and "bogus" in res.stderr
    res = invoke(runner, ["gate", "--run", str(run_dir), "--baseline", "run_remote_id"])
    assert res.exit_code == 2 and "local run directory" in res.stderr


def test_nothing_counted_is_a_platform_error_exit_3(runner, smoke_args):
    run_dir = make_run(runner, smoke_args, "--budget-usd", "0.000001", "--force")
    res = invoke(runner, ["gate", "--run", str(run_dir)])
    assert res.exit_code == 3 and "ERROR" in res.stdout


def test_local_compare_against_a_baseline_dir(runner, smoke_args, tmp_path):
    run_dir = make_run(runner, smoke_args)
    res = invoke(
        runner,
        ["gate", "--run", str(run_dir), "--baseline", str(run_dir), "--format", "json"],
    )
    assert res.exit_code == 0, res.stderr
    reg = next(g for g in json.loads(res.stdout)["gates"] if g["id"] == "regression")
    assert reg["status"] in ("pass", "warn")


def test_md_format_and_md_out(runner, smoke_args, tmp_path):
    run_dir = make_run(runner, smoke_args)
    md = tmp_path / "comment.md"
    res = invoke(runner, ["gate", "--run", str(run_dir), "--format", "md", "--md-out", str(md)])
    assert res.exit_code == 0
    assert res.stdout.splitlines()[0] == MARKER and md.read_text().startswith(MARKER)


def run_json(run_dir: Path) -> dict:
    return json.loads((run_dir / "report.json").read_text())


@respx.mock
def test_remote_gate_pass_and_fail(runner, smoke_args):
    report = run_json(make_run(runner, smoke_args))
    respx.get(f"{API}/v1/runs/run_9").mock(
        return_value=httpx.Response(
            200, json={"id": "run_9", "status": "done", "baseline_of": None}
        )
    )
    route = respx.get(f"{API}/v1/runs/run_9/report").mock(
        return_value=httpx.Response(200, json=report)
    )
    args = ["gate", "--run", "run_9", "--api-url", API, "--api-key", "gk_x"]
    assert invoke(runner, args).exit_code == 0
    assert route.calls.last.request.headers["authorization"] == "Bearer gk_x"


@respx.mock
def test_remote_incomplete_run_exits_3_and_missing_run_exits_2(runner, smoke_args):
    report = run_json(make_run(runner, smoke_args))
    respx.get(f"{API}/v1/runs/run_9").mock(
        return_value=httpx.Response(
            200, json={"id": "run_9", "status": "failed", "baseline_of": None}
        )
    )
    respx.get(f"{API}/v1/runs/run_9/report").mock(return_value=httpx.Response(200, json=report))
    respx.get(f"{API}/v1/runs/nope").mock(
        return_value=httpx.Response(404, json={"error": {"code": "not_found", "message": "gone"}})
    )
    assert invoke(runner, ["gate", "--run", "run_9", "--api-url", API]).exit_code == 3
    assert invoke(runner, ["gate", "--run", "nope", "--api-url", API]).exit_code == 2


@respx.mock
def test_remote_server_error_exits_3(runner):
    respx.get(f"{API}/v1/runs/run_9").mock(return_value=httpx.Response(503, text="down"))
    assert invoke(runner, ["gate", "--run", "run_9", "--api-url", API]).exit_code == 3


@respx.mock
def test_remote_compare_and_findings_delta_feed_the_gates(runner, smoke_args, tmp_path):
    run_dir = make_run(runner, smoke_args)
    report = run_json(run_dir)
    # a comparison document produced by the real code path, then declared a regression
    from gauntlet_cli.commands.gate import _local_data
    from gauntlet_core.eval import compare_runs

    data, _ = _local_data(run_dir)
    cmp = compare_runs(data, data).model_dump(mode="json")
    cmp["verdict"] = "regression"
    respx.get(f"{API}/v1/runs/run_9").mock(
        return_value=httpx.Response(
            200, json={"id": "run_9", "status": "done", "baseline_of": "run_0"}
        )
    )
    respx.get(f"{API}/v1/runs/run_9/report").mock(return_value=httpx.Response(200, json=report))
    respx.get(f"{API}/v1/runs/run_9/compare").mock(return_value=httpx.Response(200, json=cmp))
    respx.get(f"{API}/v1/runs/run_9/findings-delta").mock(
        return_value=httpx.Response(
            200,
            json={
                "new_by_severity": {"critical": 1},
                "new": [
                    {"id": "fnd_1", "title": "Canary leak", "severity": "critical", "category": "x"}
                ],
            },
        )
    )
    res = invoke(runner, ["gate", "--run", "run_9", "--api-url", API, "--format", "md"])
    assert res.exit_code == 1
    assert "Regression versus baseline" in res.stdout and "critical: Canary leak" in res.stdout
    assert "security.critical" in res.stdout
