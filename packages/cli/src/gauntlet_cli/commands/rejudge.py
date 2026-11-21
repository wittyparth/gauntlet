"""`gauntlet rejudge RUN_DIR`: run the judges again over the cassettes of a local run."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer
from gauntlet_core.eval import load_rubrics
from gauntlet_core.judges import MemoryJudgeCache
from gauntlet_core.llm import Gateway, LiteLLMGateway, load_config
from gauntlet_core.replay import (
    CassetteError,
    apply_outcome_rule,
    import_cassette,
    rejudge_episode,
    trajectory_from_cassette,
)
from gauntlet_core.schema import Rubric
from pydantic import ValidationError

from ..fakellm import load_fake_llm


def rejudge(
    run_dir: Annotated[Path, typer.Argument(help="A local run directory.")],
    rubrics: Annotated[
        str | None, typer.Option("--rubrics", help="Comma separated rubric ids (default: all).")
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Bypass the judge cache.")] = False,
    config: Annotated[Path | None, typer.Option(help="gauntlet.toml.")] = None,
    fake_llm: Annotated[Path | None, typer.Option("--fake-llm", hidden=True)] = None,
) -> None:
    """Re-run the judge cascade over every episode cassette in RUN_DIR and write rejudge.json.

    The cassettes (journals) are never modified; the new verdicts and the outcome recomputed
    from them are printed and saved.
    """
    files = sorted((run_dir / "episodes").glob("*.cassette.jsonl"))
    if not files:
        typer.echo(f"{run_dir}: no episode cassettes found", err=True)
        raise typer.Exit(2)
    try:
        cfg = load_config(config)
    except (FileNotFoundError, ValueError, ValidationError) as e:
        typer.echo(f"config: {e}", err=True)
        raise typer.Exit(2) from e
    gateway: Gateway = load_fake_llm(fake_llm) if fake_llm else LiteLLMGateway(cfg)
    only = {r.strip() for r in rubrics.split(",") if r.strip()} if rubrics else None
    cache = None if force else MemoryJudgeCache()
    library = load_rubrics()

    async def go() -> list[dict[str, object]]:
        episodes: list[dict[str, object]] = []
        for path in files:
            try:
                snap, man = import_cassette(path.read_text())
            except CassetteError as e:
                typer.echo(f"{path}: invalid cassette: {e}", err=True)
                raise typer.Exit(2) from e
            pool: dict[str, Rubric] = {**library, **man.rubrics}
            wanted = only if only is not None else set(man.rubrics)
            unknown = wanted - set(pool)
            if unknown:
                typer.echo(f"unknown rubric(s): {', '.join(sorted(unknown))}", err=True)
                raise typer.Exit(2)
            chosen = [pool[r] for r in sorted(wanted)]
            verdicts = await rejudge_episode(
                trajectory_from_cassette(snap, man), chosen, gateway, only=wanted,
                policy_text=man.agent_version.profile.policies_text, cache=cache,
            )  # fmt: skip
            checks = [
                (str(e.payload["check_id"]), bool(e.payload["holds"]))
                for e in snap.events
                if e.kind == "check_result"
            ]
            episodes.append(
                {
                    "episode_id": man.episode_id,
                    "scenario_id": man.scenario.id,
                    "outcome": apply_outcome_rule(checks, verdicts),
                    "verdicts": [v.model_dump(mode="json") for v in verdicts],
                }
            )
        return episodes

    episodes = asyncio.run(go())
    (run_dir / "rejudge.json").write_text(json.dumps({"episodes": episodes}, indent=2))
    for e in episodes:
        results = ", ".join(
            f"{v['criterion']}={v['result']}"
            for v in e["verdicts"]  # type: ignore[attr-defined]
        )
        typer.echo(f"{e['episode_id']}  {e['scenario_id']}  {e['outcome']}  {results}")
