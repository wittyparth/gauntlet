from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

from cli_helpers import FIXTURES, invoke
from gauntlet_cli import runlib
from gauntlet_cli.agentfile import load_agent_file
from gauntlet_cli.fakellm import ScriptedLLM, load_fake_llm
from gauntlet_cli.localdb import LocalDb
from gauntlet_core.engine import SqliteJournalStore, load_cassette, store_from_cassette
from gauntlet_core.eval import RunReport
from gauntlet_core.packs import load_pack
from gauntlet_core.runner import RunnerDeps, execute_episode


def read_report(run_dir: Path) -> RunReport:
    return RunReport.model_validate_json((run_dir / "report.json").read_text())


def test_smoke_run_exit_0_with_correct_pass_and_fail(runner, smoke_args, tmp_path: Path):
    res = invoke(runner, [*smoke_args, "--concurrency", "4"])
    assert res.exit_code == 0, res.stderr
    rep = read_report(tmp_path / "run")
    by = {s.scenario_id: s for s in rep.per_scenario}
    assert (by["scn_tiny_status"].passed, by["scn_tiny_status"].counted) == (1, 1)
    assert (by["scn_tiny_cancel"].passed, by["scn_tiny_cancel"].counted) == (0, 1)
    assert rep.counted == 2 and rep.pass_rate == 0.5 and rep.excluded == {}
    assert [f.scenario_id for f in rep.failures] == ["scn_tiny_cancel"]
    assert rep.failures[0].reasons == ["success"]
    dims = {d.criterion: d for d in rep.dimensions}
    assert (dims["task_completion"].passed, dims["task_completion"].failed) == (1, 1)
    assert dims["tone_empathy"].score == 1.0
    assert rep.caution.uncalibrated_rubrics == ["task_completion", "tone_empathy"]
    assert rep.cost_usd_micros > 0
    out = res.stdout
    assert "PASS" in out and "FAIL" in out and "scn_tiny_cancel" in out and "50%" in out
    for name in ("report.json", "report.md", "journal.db", "meta.json", "local.db"):
        assert (tmp_path / "run" / name).is_file()
    assert len(list((tmp_path / "run" / "episodes").glob("*.cassette.jsonl"))) == 2


def test_cassette_written_and_strict_replays(runner, smoke_args, tmp_path: Path):
    assert invoke(runner, smoke_args).exit_code == 0
    run_dir = tmp_path / "run"
    db = LocalDb(run_dir / "local.db")
    meta = json.loads((run_dir / "meta.json").read_text())
    row = next(e for e in db.episodes(meta["run_id"]) if e.scenario_id == "scn_tiny_status")
    text = (run_dir / "episodes" / f"{row.id}.cassette.jsonl").read_text()
    journal, _ = load_cassette(text)
    assert journal.events[-1].kind == "episode_ended"

    pack = load_pack(FIXTURES / "tinyshop")
    agent = load_agent_file(FIXTURES / "agent.yaml")
    plan = runlib.make_plan(
        run_id=meta["run_id"], out=run_dir, pack=pack, agent=agent,
        scenarios=list(pack.scenarios.values()), reps=1, seed=0, budget_micros=10**9,
        concurrency=1, judge=True, suite_id="smoke", episode_ids={row.id: (row.scenario_id, 0)},
    )  # fmt: skip

    async def replay():
        store = await store_from_cassette(text, row.id)
        silent = ScriptedLLM({})
        out = await execute_episode(
            runlib._job(plan, row.id),
            RunnerDeps(store=store, gateway=silent),
            replay_only=True,
        )
        return out, silent, [e.model_dump() for e in (await store.load(row.id)).events]

    out, silent, events = asyncio.run(replay())
    assert out.outcome == "passed" and silent.calls == []
    assert events == [e.model_dump() for e in journal.events]


def test_json_stdout_is_only_json(runner, smoke_args):
    res = invoke(runner, [*smoke_args, "--json"])
    assert res.exit_code == 0
    assert RunReport.model_validate_json(res.stdout).counted == 2


def test_fail_under(runner, smoke_args, tmp_path: Path):
    assert invoke(runner, [*smoke_args, "--fail-under", "1.0"]).exit_code == 1
    args = [*smoke_args[:-1], str(tmp_path / "run2")]
    assert invoke(runner, [*args, "--fail-under", "0.4"]).exit_code == 0


def test_no_judge_skips_dimensions(runner, smoke_args, llm_calls):
    res = invoke(runner, [*smoke_args, "--no-judge", "--json"])
    assert res.exit_code == 0
    assert RunReport.model_validate_json(res.stdout).dimensions == []
    assert "judge_small" not in llm_calls


def test_resume_of_finished_run_makes_zero_llm_calls(runner, smoke_args, tmp_path, llm_calls):
    assert invoke(runner, smoke_args).exit_code == 0
    first = len(llm_calls)
    assert first > 0
    before = read_report(tmp_path / "run").model_dump()
    res = invoke(runner, [*smoke_args, "--resume", str(tmp_path / "run")])
    assert res.exit_code == 0, res.stderr
    assert len(llm_calls) == first
    assert read_report(tmp_path / "run").model_dump() == before


def recorded_llm_effects(journal: Path) -> int:
    con = sqlite3.connect(journal)
    try:
        rows = con.execute("SELECT key, status FROM effects").fetchall()
    finally:
        con.close()
    return sum(1 for k, s in rows if k.startswith("llm:") and s == "done")


def test_crash_and_resume_does_not_repeat_completed_llm_effects(
    runner, smoke_args, tmp_path, monkeypatch, llm_calls
):
    clean_args = [*smoke_args[:-1], str(tmp_path / "clean")]
    assert invoke(runner, [*clean_args, "--concurrency", "1"]).exit_code == 0
    clean_calls = len(llm_calls)
    clean_report = read_report(tmp_path / "clean")
    llm_calls.clear()

    real_append = SqliteJournalStore.append
    appends = 0

    async def dying_append(self, *a, **kw):
        nonlocal appends
        appends += 1
        if appends == 14:
            raise KeyboardInterrupt  # the process "dies" mid-run
        return await real_append(self, *a, **kw)

    monkeypatch.setattr(SqliteJournalStore, "append", dying_append)
    res = invoke(runner, [*smoke_args, "--concurrency", "1"])
    assert res.exit_code == 130
    first_calls = len(llm_calls)
    run_dir = tmp_path / "run"
    assert not (run_dir / "report.json").exists()
    recorded = recorded_llm_effects(run_dir / "journal.db")
    assert 0 < recorded < clean_calls

    monkeypatch.setattr(SqliteJournalStore, "append", real_append)
    llm_calls.clear()
    res = invoke(runner, [*smoke_args, "--resume", str(run_dir), "--concurrency", "1"])
    assert res.exit_code == 0, res.stderr
    assert len(llm_calls) == clean_calls - recorded  # nothing already recorded is repeated
    assert first_calls <= recorded + 1  # at most the in-flight call was lost
    resumed = read_report(run_dir)
    assert [(s.scenario_id, s.passed, s.counted) for s in resumed.per_scenario] == [
        (s.scenario_id, s.passed, s.counted) for s in clean_report.per_scenario
    ]
    assert resumed.pass_rate == clean_report.pass_rate


def test_unknown_suite_and_bad_resume_dir_exit_2(runner, smoke_args, tmp_path):
    assert invoke(runner, [*smoke_args[:4], "--suite", "nope", *smoke_args[5:]]).exit_code == 2
    res = invoke(runner, [*smoke_args, "--resume", str(tmp_path / "empty")])
    assert res.exit_code == 2


def test_default_suite_is_smoke_when_present(runner, pack, tmp_path):
    args = [
        "run",
        str(pack),
        "--target",
        str(FIXTURES / "agent.yaml"),
        "--fake-llm",
        str(FIXTURES / "fake_llm_smoke.yaml"),
        "--out",
        str(tmp_path / "r"),
        "--json",
    ]
    assert invoke(runner, args).exit_code == 0


def test_fake_llm_file_is_stateless_by_assistant_count():
    from gauntlet_core.sim import SimOutput

    llm = load_fake_llm(FIXTURES / "fake_llm_smoke.yaml")
    base = [{"role": "system", "content": "find out where order ord_1 is"}]

    async def go():
        a = await llm.complete("simulator", base, response_model=SimOutput)
        again = [*base, {"role": "assistant", "content": "x"}]
        b = await llm.complete("simulator", again, response_model=SimOutput)
        return a, b

    a, b = asyncio.run(go())
    assert isinstance(a.parsed, SimOutput) and a.parsed.action == "say"
    assert isinstance(b.parsed, SimOutput) and b.parsed.action == "done"
