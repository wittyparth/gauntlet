"""`gauntlet run`: execute a pack suite against an agent in local SQLite mode."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from gauntlet_core.estimate import estimate_run_cost
from gauntlet_core.ids import new_id
from gauntlet_core.llm import Gateway, LiteLLMGateway, load_config
from gauntlet_core.packs import Pack, PackError, load_pack
from gauntlet_core.render import fmt_usd, render_markdown
from gauntlet_core.runner import EpisodeOutcome
from gauntlet_core.schema import RunManifest
from gauntlet_core.validate import validate_pack
from pydantic import ValidationError
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn

from ..agentfile import AgentFile, load_agent_file
from ..fakellm import load_fake_llm
from ..localdb import LocalDb
from ..output import print_report
from ..runlib import (
    RunPlan,
    Timer,
    build_report,
    execute_plan,
    make_plan,
    now_iso,
    read_meta,
    write_meta,
)
from .report import RUNS_DIR

PLATFORM_VERSION = "0.1.0"


def _die(msg: str, code: int = 2) -> typer.Exit:
    typer.echo(msg, err=True)
    return typer.Exit(code)


def _load_inputs(pack_dir: Path, target: Path) -> tuple[Pack, AgentFile]:
    try:
        pack = load_pack(pack_dir)
    except PackError as e:
        for issue in e.issues:
            typer.echo(f"{pack_dir}:pack_error:{issue}", err=True)
        raise typer.Exit(2) from e
    issues = validate_pack(pack)
    if issues:
        for i in issues:
            typer.echo(f"{pack_dir / i.path}:{i.code}:{i.message}", err=True)
        raise typer.Exit(2)
    try:
        agent = load_agent_file(target)
    except (OSError, ValidationError, ValueError) as e:
        raise _die(f"{target}:agent_file:{str(e).splitlines()[0]}") from e
    return pack, agent


def run(
    pack: Annotated[Path, typer.Argument(help="Pack directory.")],
    target: Annotated[Path, typer.Option("--target", help="agent.yaml.")],
    suite: Annotated[str | None, typer.Option(help="Suite id (default: smoke, else all).")] = None,
    reps: Annotated[int | None, typer.Option(help="Repetitions per scenario.")] = None,
    budget_usd: Annotated[float, typer.Option("--budget-usd", help="Spend cap in USD.")] = 2.0,
    concurrency: Annotated[int, typer.Option(min=1, help="Parallel episodes.")] = 4,
    seed: Annotated[int, typer.Option(help="Run seed.")] = 0,
    out: Annotated[Path | None, typer.Option(help="Output dir.")] = None,
    json_out: Annotated[
        bool, typer.Option("--json", help="Only RunReport JSON on stdout.")
    ] = False,
    fail_under: Annotated[float | None, typer.Option("--fail-under", min=0.0, max=1.0)] = None,
    no_judge: Annotated[bool, typer.Option("--no-judge", help="Skip the judge stage.")] = False,
    resume: Annotated[Path | None, typer.Option("--resume", help="Resume a run dir.")] = None,
    config: Annotated[Path | None, typer.Option(help="gauntlet.toml.")] = None,
    force: Annotated[bool, typer.Option("--force", help="Ignore the budget pre-check.")] = False,
    fake_llm: Annotated[Path | None, typer.Option("--fake-llm", hidden=True)] = None,
) -> None:
    """Run PACK against the agent in --target and print a report.

    Exit codes: 0 run completed (and --fail-under met, if given); 1 --fail-under not met;
    2 usage or validation error; 3 platform failure (budget exhausted before completion, zero
    counted episodes, runner crash); 130 interrupted (journals intact, use --resume).
    """
    pack_obj, agent = _load_inputs(pack, target)
    try:
        cfg = load_config(config)
    except (FileNotFoundError, ValueError, ValidationError) as e:
        raise _die(f"config: {e}") from e
    gateway: Gateway = load_fake_llm(fake_llm) if fake_llm else LiteLLMGateway(cfg)

    meta: dict[str, Any] = {}
    if resume is not None:
        if not (resume / "meta.json").is_file():
            raise _die(f"{resume}: not a run directory (no meta.json)")
        meta = read_meta(resume / "meta.json")
        suite, reps, seed = meta["suite"], meta["reps"], meta["seed"]
        budget_usd = meta["budget_usd"]
    if suite is None:
        suite = "smoke" if "smoke" in pack_obj.suites else "all"
    if suite == "all" and "all" not in pack_obj.suites:
        scn_ids = list(pack_obj.scenarios)
        suite_reps = 1
    elif suite in pack_obj.suites:
        scn_ids = pack_obj.suites[suite].scenarios
        suite_reps = pack_obj.suites[suite].repetitions
    else:
        raise _die(f"unknown suite {suite!r}; available: {sorted(pack_obj.suites)}")
    reps = reps or suite_reps
    scenarios = [pack_obj.scenarios[s] for s in scn_ids]
    budget_micros = round(budget_usd * 1_000_000)

    agent_model = getattr(agent.target, "model", None)
    est = estimate_run_cost(scenarios, reps, cfg, agent_model=agent_model)
    if resume is None and est.low > budget_micros and not force:
        raise _die(
            f"estimated cost {fmt_usd(est.low)} to {fmt_usd(est.high)} exceeds the budget "
            f"{fmt_usd(budget_micros)}; raise --budget-usd or pass --force",
            3,
        )

    run_id = meta.get("run_id") or new_id("run")
    out_dir = resume or out or RUNS_DIR / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    db = LocalDb(out_dir / "local.db")
    if resume is None:
        episodes = {new_id("ep"): (s.id, rep) for s in scenarios for rep in range(reps)}
    else:
        episodes = {e.id: (e.scenario_id, e.rep) for e in db.episodes(run_id)}
    plan = make_plan(
        run_id=run_id, out=out_dir, pack=pack_obj, agent=agent, scenarios=scenarios, reps=reps,
        seed=seed, budget_micros=budget_micros, concurrency=concurrency, judge=not no_judge,
        suite_id=suite, episode_ids=episodes,
    )  # fmt: skip
    if resume is None:
        _record_run(plan, db, cfg.llm.roles, est.expected)
    return _drive(plan, db, gateway, cfg, json_out, fail_under, meta_extra=est.warnings)


def _record_run(plan: RunPlan, db: LocalDb, roles: Any, expected: int) -> None:
    manifest = RunManifest(
        run_id=plan.run_id,
        suite_id=plan.suite_id,
        agent_version=plan.agent,
        scenario_versions={s.id: s.version for s in plan.scenarios},
        seed=plan.seed,
        repetitions=plan.reps,
        model_roles={k: v.model for k, v in roles.items()},
        rubric_versions={},
        platform_version=PLATFORM_VERSION,
        budget_usd_micros=plan.budget_micros,
        created_at=datetime.now(UTC),
    )
    db.add_run(plan.run_id, now_iso(), manifest.model_dump_json(), "running")
    for ep_id, (scn_id, rep) in plan.episodes.items():
        db.add_episode(ep_id, plan.run_id, scn_id, rep)
    write_meta(
        plan.out / "meta.json",
        {
            "run_id": plan.run_id,
            "suite": plan.suite_id,
            "reps": plan.reps,
            "seed": plan.seed,
            "budget_usd": plan.budget_micros / 1_000_000,
            "pack": str(plan.pack.root),
            "estimated_usd_micros": expected,
            "manifest": manifest.model_dump(mode="json"),
        },
    )


def _drive(
    plan: RunPlan,
    db: LocalDb,
    gateway: Gateway,
    cfg: Any,
    json_out: bool,
    fail_under: float | None,
    meta_extra: Any = (),
) -> None:
    err = Console(stderr=True)
    timer = Timer()
    todo = sum(1 for e in db.episodes(plan.run_id) if e.outcome is None)
    spent = 0
    columns = [
        TextColumn("[bold]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TextColumn("{task.fields[cost]}"),
    ]
    progress = Progress(*columns, console=err, transient=True)
    task = progress.add_task("episodes", total=todo, cost=fmt_usd(0))

    def on_done(ep_id: str, out: EpisodeOutcome) -> None:
        nonlocal spent
        spent += out.cost.usd_micros
        progress.update(task, advance=1, cost=fmt_usd(spent))

    try:
        with progress:
            asyncio.run(execute_plan(plan, gateway, db, on_done=on_done))
    except KeyboardInterrupt:
        db.set_status(plan.run_id, "interrupted")
        err.print(f"interrupted; resume with: gauntlet run ... --resume {plan.out}")
        raise typer.Exit(130) from None
    except Exception as e:
        db.set_status(plan.run_id, "failed")
        err.print(f"runner crashed: {type(e).__name__}: {e}")
        raise typer.Exit(3) from e

    judge_model = cfg.llm.roles["judge_small"].model
    report = build_report(
        plan, db, judge_model=judge_model,
        unpriced_models=sorted(getattr(gateway, "unpriced_models", set())),
    )  # fmt: skip
    db.set_status(plan.run_id, "done")
    display = {
        "pack": plan.pack.id,
        "target": getattr(plan.agent.target, "model", plan.agent.target.kind),
        "suite": plan.suite_id,
        "repetitions": plan.reps,
        "duration_s": timer.elapsed(),
    }
    meta = read_meta(plan.out / "meta.json")
    write_meta(plan.out / "meta.json", {**meta, "display": display, "warnings": list(meta_extra)})
    (plan.out / "report.json").write_text(report.model_dump_json(indent=2))
    (plan.out / "report.md").write_text(render_markdown(report, display))
    if json_out:
        typer.echo(report.model_dump_json(indent=2))
    else:
        print_report(report, display, Console())
        err.print(f"run dir: {plan.out}")
    db.close()

    if report.excluded.get("budget_exhausted") or report.counted == 0:
        raise typer.Exit(3)
    if fail_under is not None and (report.pass_rate is None or report.pass_rate < fail_under):
        raise typer.Exit(1)
