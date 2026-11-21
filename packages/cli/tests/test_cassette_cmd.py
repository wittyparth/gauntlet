"""`gauntlet cassette export|import`, `gauntlet replay` and `gauntlet rejudge`."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import respx
from cli_helpers import FIXTURES, invoke
from gauntlet_core.replay import import_cassette

API = "http://api.test"


def run_dir_cassettes(run_dir: Path) -> list[Path]:
    return sorted((run_dir / "episodes").glob("*.cassette.jsonl"))


def make_run(runner, smoke_args) -> Path:
    assert invoke(runner, smoke_args).exit_code == 0
    return Path(smoke_args[-1])


def cassette_for(run_dir: Path, scenario: str) -> Path:
    for p in run_dir_cassettes(run_dir):
        _, man = import_cassette(p.read_text())
        if man.scenario.id == scenario:
            return p
    raise AssertionError(scenario)


def test_local_run_cassettes_carry_a_full_manifest(runner, smoke_args):
    run_dir = make_run(runner, smoke_args)
    snap, man = import_cassette(run_dir_cassettes(run_dir)[0].read_text())
    assert man.scenario.id.startswith("scn_tiny") and man.world.tools and man.persona.id
    assert snap.events[-1].kind == "episode_ended"


@respx.mock
def test_export_writes_the_file_and_sends_the_key(runner, tmp_path):
    route = respx.get(f"{API}/v1/episodes/ep_1/cassette").mock(
        return_value=httpx.Response(200, text='{"t":"header"}\n')
    )
    out = tmp_path / "ep.jsonl"
    res = invoke(
        runner,
        ["cassette", "export", "ep_1", "-o", str(out), "--api-url", API, "--api-key", "gk_x"],
    )
    assert res.exit_code == 0, res.stderr
    assert out.read_text() == '{"t":"header"}\n'
    assert route.calls.last.request.headers["authorization"] == "Bearer gk_x"


@respx.mock
def test_export_reports_http_errors(runner, tmp_path):
    respx.get(f"{API}/v1/episodes/nope/cassette").mock(
        return_value=httpx.Response(404, json={"error": {"code": "not_found", "message": "gone"}})
    )
    res = invoke(
        runner,
        [
            "cassette",
            "export",
            "nope",
            "-o",
            str(tmp_path / "x"),
            "--api-url",
            API,
            "--api-key",
            "k",
        ],
    )
    assert res.exit_code == 1 and "not_found" in res.stderr
    assert not (tmp_path / "x").exists()


@respx.mock
def test_import_posts_the_file_and_prints_the_ids(runner, tmp_path):
    f = tmp_path / "c.jsonl"
    f.write_text('{"t":"header"}\n')
    route = respx.post(f"{API}/v1/cassettes").mock(
        return_value=httpx.Response(201, json={"run_id": "run_9", "episode_id": "ep_9"})
    )
    res = invoke(runner, ["cassette", "import", str(f), "--api-url", API, "--api-key", "k"])
    assert res.exit_code == 0 and "ep_9" in res.stdout
    assert route.calls.last.request.content == b'{"t":"header"}\n'


def test_strict_replay_exits_0_and_a_tampered_cassette_exits_1(runner, smoke_args, tmp_path):
    run_dir = make_run(runner, smoke_args)
    cassette = cassette_for(run_dir, "scn_tiny_status")
    res = invoke(runner, ["replay", str(cassette), "--mode", "strict"])
    assert res.exit_code == 0, res.stdout + res.stderr
    assert "identical" in res.stdout
    lines = cassette.read_text().splitlines()
    tampered = []
    for line in lines:
        row = json.loads(line)
        if row["t"] == "effect" and "has shipped" in json.dumps(row.get("result")):
            row["result"] = json.loads(json.dumps(row["result"]).replace("has shipped", "is lost"))
        tampered.append(json.dumps(row))
    bad = tmp_path / "bad.jsonl"
    bad.write_text("\n".join(tampered) + "\n")
    res = invoke(runner, ["replay", str(bad), "--mode", "strict"])
    assert res.exit_code == 1 and "diverge" in res.stdout.lower()
    assert invoke(runner, ["replay", str(tmp_path / "missing.jsonl")]).exit_code == 2


def test_agent_live_replay_with_the_same_agent_makes_no_model_calls(runner, smoke_args, llm_calls):
    run_dir = make_run(runner, smoke_args)
    llm_calls.clear()
    cassette = cassette_for(run_dir, "scn_tiny_status")
    res = invoke(
        runner,
        ["replay", str(cassette), "--mode", "agent_live", "--target", str(FIXTURES / "agent.yaml"),
         "--fake-llm", str(FIXTURES / "fake_llm_smoke.yaml")],
    )  # fmt: skip
    assert res.exit_code == 0, res.stdout + res.stderr
    assert llm_calls == [] and "outcome: passed" in res.stdout and "no divergence" in res.stdout


def test_agent_live_replay_requires_a_target(runner, smoke_args):
    run_dir = make_run(runner, smoke_args)
    cassette = cassette_for(run_dir, "scn_tiny_status")
    assert invoke(runner, ["replay", str(cassette), "--mode", "agent_live"]).exit_code == 2


def test_rejudge_loops_over_the_cassettes_of_a_run_dir(runner, smoke_args, llm_calls):
    run_dir = make_run(runner, smoke_args)
    llm_calls.clear()
    res = invoke(
        runner,
        ["rejudge", str(run_dir), "--rubrics", "tone_empathy",
         "--fake-llm", str(FIXTURES / "fake_llm_smoke.yaml")],
    )  # fmt: skip
    assert res.exit_code == 0, res.stdout + res.stderr
    assert set(llm_calls) == {"judge_small"} and len(llm_calls) == 2  # one per episode
    out = json.loads((run_dir / "rejudge.json").read_text())
    assert len(out["episodes"]) == 2
    assert all([v["criterion"] for v in e["verdicts"]] == ["tone_empathy"] for e in out["episodes"])
    assert "tone_empathy" in res.stdout
    # the in-process judge cache dedupes identical trajectories; --force bypasses it
    llm_calls.clear()
    invoke(
        runner,
        ["rejudge", str(run_dir), "--rubrics", "tone_empathy",
         "--fake-llm", str(FIXTURES / "fake_llm_smoke.yaml"), "--force"],
    )  # fmt: skip
    assert len(llm_calls) == 2
    assert invoke(runner, ["rejudge", str(run_dir / "nope")]).exit_code == 2
