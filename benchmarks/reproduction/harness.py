"""Reproduction harness: run an imported benchmark pack against a catalog model through the
`gauntlet run` machinery and write a result file with pass^k (with intervals), per-task outcomes
and the list of deviations from the published setup.

Live runs are manual: they need `GAUNTLET_LIVE_BUDGET_USD` (a hard cap passed to the run) and a
catalog model. A run with `cassette_dir` replays a committed scripted transcript (the FakeLLM
format of `gauntlet_core.llm.scripted`) and needs no cap, no network and spends nothing.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from gauntlet_cli.main import app as cli
from gauntlet_core.eval import RunReport
from gauntlet_core.llm import load_config
from gauntlet_core.llm.catalog import catalog_model
from gauntlet_core.packs import load_pack
from pydantic import BaseModel, ConfigDict
from typer.testing import CliRunner

__all__ = [
    "CONFIG",
    "BudgetRequired",
    "ModelNotAllowed",
    "ReproResult",
    "result_path",
    "run_suite",
]

HERE = Path(__file__).parent
CONFIG = HERE / "config.yaml"
RESULTS = HERE / "results"
BUDGET_ENV = "GAUNTLET_LIVE_BUDGET_USD"
SYSTEM_PREFIX = (
    "You are a customer service agent. Follow the policy below exactly. Use the tools to look "
    "up and change records; ask the user for what you need.\n\n"
)


class BudgetRequired(SystemExit):
    """A live run needs a spend cap."""


class ModelNotAllowed(SystemExit):
    """Only models of the catalog (cheap models) are run."""


class TaskOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: str
    passed: int
    trials: int


class PassK(BaseModel):
    model_config = ConfigDict(extra="forbid")
    k: int
    value: float
    ci_low: float
    ci_high: float
    scenarios: int


class ReproResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int = 1
    suite: str
    model: str
    trials: int
    smoke: bool
    mode: str  # "live" or "cassette"
    run_id: str
    pack: dict[str, Any]
    passk: list[PassK]
    tasks: list[TaskOutcome]
    deviations: list[str]
    published: list[dict[str, Any]]
    cost_usd_micros: int
    budget_usd: float | None


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")


def result_path(suite: str, model: str, results_dir: Path = RESULTS) -> Path:
    return results_dir / f"{suite}-{slug(model)}.json"


def resolve_budget(env: Mapping[str, str], *, cassette: bool) -> float | None:
    """The spend cap for a live run; refuses without one. Cassette runs spend nothing."""
    raw = env.get(BUDGET_ENV, "").strip()
    if cassette:
        return float(raw) if raw else None
    try:
        cap = float(raw)
    except ValueError:
        cap = 0.0
    if cap <= 0:
        raise BudgetRequired(
            f"refusing to run live: set {BUDGET_ENV} to a positive USD cap (live runs are manual "
            "and need the lead's go)"
        )
    return cap


def deviations(pack_meta: Mapping[str, Any], sim_model: str, mode: str) -> list[str]:
    """Every known difference from the published setup, so a gap is never silently explained."""
    out = [
        f"user simulator: catalog role `simulator` ({sim_model}); the benchmark's own user "
        "simulator is a different (frontier) model",
        "agent prompt: the pack policy text under a one-paragraph instruction, not the "
        "benchmark's own agent prompt",
        "tool formatting: tools are exposed through the gateway's function-calling format; "
        "tool outputs are our reviewed pure ports, serialised as JSON",
        "success: one `state` check per changed record field plus required-output regexes "
        "(thousands commas tolerated), not full database hash equality; extra unintended "
        "writes are not scored",
        "judge: off (`--no-judge`); scores come only from the deterministic checks",
        "turn limit: scenario `max_turns` (30 for tau-bench, 12 for AgentDojo)",
        "temperature: gateway default for the target (the hosted target sets 0.0)",
    ]
    skipped = int(pack_meta.get("tasks", 0)) - int(pack_meta.get("portable", 0))
    if skipped:
        out.append(
            f"task coverage: {skipped} of {pack_meta.get('tasks')} upstream tasks are not "
            f"portable ({pack_meta.get('portable_pct')}% portable) and are excluded"
        )
    if mode == "cassette":
        out.append("replayed from a scripted transcript: a harness check, not a measurement")
    return out


def published_for(config: Mapping[str, Any], suite: str, model: str) -> list[dict[str, Any]]:
    """Published numbers of the suite, marked comparable only when the same model was run."""
    rows = []
    for p in config["suites"][suite].get("published") or []:
        rows.append({**p, "comparable": p.get("model") == model})
    return rows


def _agent_file(path: Path, model: str, policy: str) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "label": f"repro-{slug(model)}",
                "target": {
                    "kind": "hosted",
                    "model": model,
                    "system_prompt": SYSTEM_PREFIX + policy,
                    "temperature": 0.0,
                },
            }
        )
    )


def run_suite(
    *,
    suite: str,
    model: str,
    trials: int,
    smoke: bool = False,
    pack_dir: Path | None = None,
    out_dir: Path | None = None,
    results_dir: Path = RESULTS,
    cassette_dir: Path | None = None,
    config_path: Path = CONFIG,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Run `suite` and write `results/<suite>-<model>.json`; returns its path."""
    env = os.environ if env is None else env
    config = yaml.safe_load(config_path.read_text())
    if suite not in config["suites"]:
        raise SystemExit(f"unknown suite {suite!r}; known: {sorted(config['suites'])}")
    if catalog_model(model) is None:
        raise ModelNotAllowed(f"{model!r} is not a catalog model; only catalog models are run")
    if trials < 1:
        raise SystemExit("--trials must be at least 1")
    budget = resolve_budget(env, cassette=cassette_dir is not None)
    pack_path = Path(pack_dir or config["suites"][suite]["pack"])
    if not (pack_path / "pack.yaml").is_file():
        raise SystemExit(
            f"no imported pack at {pack_path}; run the importer first "
            f"({config['suites'][suite].get('importer', 'see README')})"
        )
    pack = load_pack(pack_path)
    work = Path(out_dir or results_dir / ".work" / f"{suite}-{slug(model)}")
    work.mkdir(parents=True, exist_ok=True)
    agent = work / "agent.yaml"
    _agent_file(agent, model, pack.policy_text)
    args = ["run", str(pack_path), "--target", str(agent), "--reps", str(trials)]
    args += ["--suite", "smoke" if smoke and "smoke" in pack.suites else "full"]
    args += ["--no-judge", "--json", "--out", str(work / "run")]
    mode = "live"
    if cassette_dir is not None:
        cassette = Path(cassette_dir) / f"{suite}-smoke.yaml"
        if not cassette.is_file():
            raise SystemExit(f"no cassette {cassette}")
        args += ["--fake-llm", str(cassette)]
        mode = "cassette"
    if budget is not None:
        args += ["--budget-usd", str(budget)]
    res = CliRunner().invoke(cli, args)
    if res.exit_code != 0:
        raise SystemExit(f"run failed (exit {res.exit_code}): {res.stderr or res.stdout}"[:2000])
    report = RunReport.model_validate_json(res.stdout)
    sim = load_config(None).llm.roles["simulator"].model
    points = [
        PassK(k=p.k, value=p.value, ci_low=p.ci_low, ci_high=p.ci_high, scenarios=p.scenarios)
        for p in report.reliability
    ]
    if not points and report.pass_rate is not None:  # a single trial: only k=1 exists
        points = [
            PassK(
                k=1,
                value=report.pass_rate,
                ci_low=report.ci_low if report.ci_low is not None else report.pass_rate,
                ci_high=report.ci_high if report.ci_high is not None else report.pass_rate,
                scenarios=len(report.per_scenario),
            )
        ]
    meta = yaml.safe_load((pack_path / "pack.yaml").read_text()).get("import", {})
    result = ReproResult(
        suite=suite,
        model=model,
        trials=trials,
        smoke=smoke,
        mode=mode,
        run_id=report.run_id,
        pack=meta,
        passk=points,
        tasks=[
            TaskOutcome(scenario_id=s.scenario_id, passed=s.passed, trials=s.counted)
            for s in report.per_scenario
        ],
        deviations=deviations(meta, sim, mode),
        published=published_for(config, suite, model),
        cost_usd_micros=report.cost_usd_micros,
        budget_usd=budget,
    )
    path = result_path(suite, model, results_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.model_dump_json(indent=2) + "\n")
    return path
