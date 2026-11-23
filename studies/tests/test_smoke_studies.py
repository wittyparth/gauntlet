"""Each study's --smoke configuration runs from scripted brains or fixtures and writes a valid
result. No model, no network."""

import importlib

import pytest

from studies.common import StudyResult, run_cli

NAMES = [
    "dva_recall",
    "judge_agreement",
    "reproducibility",
    "cost_per_1000",
    "simulator_fidelity",
    "head_to_head",
]


@pytest.mark.parametrize("name", NAMES)
def test_smoke_writes_a_valid_result(name, tmp_path):
    mod = importlib.import_module(f"studies.{name}")
    out = tmp_path / f"{name}.json"
    rc = run_cli(name, mod.build, ["--smoke", "--out", str(out)])
    assert rc == 0
    r = StudyResult.model_validate_json(out.read_text())
    assert r.name == name and r.smoke and r.limitations


def test_dva_control_files_zero_findings(tmp_path):
    from studies.dva_recall import build

    out = tmp_path / "r.json"
    run_cli("dva_recall", build, ["--smoke", "--out", str(out)])
    r = StudyResult.model_validate_json(out.read_text())
    assert r.metrics["false_positives_on_clean.sql"] == 0.0


def test_reproducibility_replays_identically(tmp_path):
    from studies.reproducibility import build

    out = tmp_path / "r.json"
    run_cli("reproducibility", build, ["--smoke", "--out", str(out)])
    assert StudyResult.model_validate_json(out.read_text()).metrics["replay_identical"] == 1.0


def test_live_run_without_inputs_refuses():
    import asyncio

    from studies.judge_agreement import build

    with pytest.raises(SystemExit):
        asyncio.run(build(0, False))
