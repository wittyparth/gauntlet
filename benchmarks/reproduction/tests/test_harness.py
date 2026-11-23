"""Reproduction harness: the smoke subset replays from a committed transcript, the result file is
valid, intervals and deviations are present, a live run refuses without a budget cap, and nothing
touches the network."""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest
import yaml

from benchmarks.reproduction.harness import (
    BudgetRequired,
    ModelNotAllowed,
    ReproResult,
    resolve_budget,
    result_path,
    run_suite,
)
from benchmarks.reproduction.report import render
from tools.import_benchmarks.tau_bench import PIN, import_tau_bench

FIX = Path(__file__).parents[3] / "tests" / "fixtures" / "benchmarks"
MODEL = "openrouter/qwen/qwen3.7-flash"


@pytest.fixture(scope="module")
def pack(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("repro") / "taubench_retail"
    import_tau_bench(FIX / "tau_mini", out, pin=PIN)
    return out


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def smoke(pack: Path, tmp_path: Path, **kw) -> Path:
    return run_suite(
        suite="taubench_retail",
        model=MODEL,
        trials=2,
        smoke=True,
        pack_dir=pack,
        out_dir=tmp_path / "work",
        results_dir=tmp_path / "results",
        cassette_dir=FIX / "cassettes",
        env={},
        **kw,
    )


def test_smoke_subset_runs_from_the_transcript_with_a_valid_result_file(pack, tmp_path, no_network):
    path = smoke(pack, tmp_path)
    assert path == result_path("taubench_retail", MODEL, tmp_path / "results")
    result = ReproResult.model_validate(json.loads(path.read_text()))
    assert result.mode == "cassette" and result.smoke and result.trials == 2
    assert {t.scenario_id for t in result.tasks} == {f"tau_retail_00{i}" for i in range(4)}
    assert all(t.trials == 2 and t.passed == 2 for t in result.tasks)
    by_k = {p.k: p for p in result.passk}
    assert set(by_k) == {1, 2} and by_k[1].value == 1.0
    assert all(0.0 <= p.ci_low <= p.value <= p.ci_high <= 1.0 for p in result.passk)
    assert result.pack["pin"] == PIN and result.pack["portable_pct"] == 57.1
    assert result.cost_usd_micros == 0 and result.budget_usd is None


def test_deviations_are_listed(pack, tmp_path, no_network):
    result = ReproResult.model_validate_json(smoke(pack, tmp_path).read_text())
    text = "\n".join(result.deviations)
    for needle in ("user simulator", "agent prompt", "tool formatting", "judge", "turn limit"):
        assert needle in text
    assert "3 of 7 upstream tasks are not portable" in text
    assert "replayed from a scripted transcript" in text


def test_report_marks_published_numbers_as_context_unless_comparable(pack, tmp_path, no_network):
    smoke(pack, tmp_path)
    cfg = yaml.safe_load((Path(__file__).parents[1] / "config.yaml").read_text())
    cfg["suites"]["taubench_retail"]["published"] = [
        {"model": "some-frontier-model", "value": 0.6, "source": "paper", "date": "2026-01-01"}
    ]
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg))
    text = render(tmp_path / "results", path)
    assert "context only, no pass or fail" in text and "100.0%" in text
    cfg["suites"]["taubench_retail"]["published"][0]["model"] = MODEL
    path.write_text(yaml.safe_dump(cfg))
    assert "gap +40.0 pts, outside, explain in writing" in render(tmp_path / "results", path)


def test_live_run_refuses_without_a_budget_cap(pack, tmp_path):
    for env in ({}, {"GAUNTLET_LIVE_BUDGET_USD": "0"}, {"GAUNTLET_LIVE_BUDGET_USD": "x"}):
        with pytest.raises(BudgetRequired, match="GAUNTLET_LIVE_BUDGET_USD"):
            run_suite(
                suite="taubench_retail",
                model=MODEL,
                trials=1,
                pack_dir=pack,
                results_dir=tmp_path / "r",
                env=env,
            )
    assert resolve_budget({"GAUNTLET_LIVE_BUDGET_USD": "1.5"}, cassette=False) == 1.5


def test_only_catalog_models_are_accepted(pack, tmp_path):
    with pytest.raises(ModelNotAllowed):
        run_suite(
            suite="taubench_retail",
            model="not/a-catalog-model",
            trials=1,
            pack_dir=pack,
            results_dir=tmp_path,
            env={"GAUNTLET_LIVE_BUDGET_USD": "1"},
        )


def test_missing_pack_points_at_the_importer(tmp_path):
    with pytest.raises(SystemExit, match="run the importer first"):
        run_suite(
            suite="taubench_retail",
            model=MODEL,
            trials=1,
            pack_dir=tmp_path / "none",
            results_dir=tmp_path,
            cassette_dir=FIX / "cassettes",
            env={},
        )
