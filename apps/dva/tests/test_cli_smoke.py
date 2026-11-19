"""`gauntlet run packs/ecommerce` over the smoke suite against the DVA (scripted brain, wired),
with a scripted simulator (`--fake-llm`) and no judge. No live model."""

from __future__ import annotations

from pathlib import Path

import yaml
from dva_helpers import REPO, serve_dva_thread
from gauntlet_cli.main import app
from gauntlet_core.eval import RunReport
from typer.testing import CliRunner

FAKE = Path(__file__).parent / "fixtures" / "fake_llm_smoke.yaml"


def run_smoke(tmp_path: Path, flaws: set[str]) -> RunReport:
    with serve_dva_thread(lambda: flaws) as url:
        agent = tmp_path / "agent.yaml"
        agent.write_text(
            yaml.safe_dump(
                {
                    "label": "dva-wired",
                    "target": {
                        "kind": "openai_compat",
                        "base_url": f"{url}/v1",
                        "model": "dva",
                        "wired": True,
                    },
                }
            )
        )
        args = [
            "run",
            str(REPO / "packs" / "ecommerce"),
            "--target",
            str(agent),
            "--suite",
            "smoke",
            "--fake-llm",
            str(FAKE),
            "--no-judge",
            "--json",
            "--out",
            str(tmp_path / "run"),
        ]
        res = CliRunner().invoke(app, args)
    assert res.exit_code == 0, res.stderr
    return RunReport.model_validate_json(res.stdout)


def passed(report: RunReport) -> dict[str, int]:
    return {s.scenario_id: s.passed for s in report.per_scenario}


def test_smoke_against_the_fixed_dva_passes_everything(tmp_path):
    report = run_smoke(tmp_path, set())
    assert report.counted == 10 and report.excluded == {}
    assert all(passed(report).values()), passed(report)


def test_smoke_against_the_flawed_dva_fails_the_trap_scenarios(tmp_path):
    report = run_smoke(tmp_path, {"F01", "F02", "F06", "F13"})
    result = passed(report)
    for scn in ("06", "07", "08", "14", "17"):
        assert result[f"scn_ecom_{scn}"] == 0, scn
    for scn in ("01", "02", "03", "04", "05"):
        assert result[f"scn_ecom_{scn}"] == 1, scn
    assert report.pass_rate == 0.5
