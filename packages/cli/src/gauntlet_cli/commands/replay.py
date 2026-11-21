"""`gauntlet replay FILE`: strict replay (exact, no model) or agent_live replay."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Literal

import typer
from gauntlet_core.engine import MemoryBudgetLedger, MemoryJournalStore
from gauntlet_core.llm import Gateway, LiteLLMGateway, load_config
from gauntlet_core.replay import (
    CassetteError,
    first_live_seq,
    import_cassette,
    replay_agent_live,
    replay_strict,
)
from gauntlet_core.runner import RunnerDeps
from gauntlet_core.schema import AgentVersion
from gauntlet_core.targets import UrlPolicy
from pydantic import ValidationError

from ..agentfile import load_agent_file
from ..fakellm import load_fake_llm


def _read(file: Path) -> str:
    try:
        text = file.read_text()
        import_cassette(text)  # fail early, with the line number
    except OSError as e:
        typer.echo(f"{file}: {e.strerror or e}", err=True)
        raise typer.Exit(2) from e
    except CassetteError as e:
        typer.echo(f"{file}: invalid cassette: {e}", err=True)
        raise typer.Exit(2) from e
    return text


def replay(
    file: Annotated[Path, typer.Argument(help="Cassette file.")],
    mode: Annotated[
        Literal["strict", "agent_live"], typer.Option("--mode", help="strict or agent_live.")
    ] = "strict",
    target: Annotated[
        Path | None, typer.Option("--target", help="agent.yaml (agent_live).")
    ] = None,
    config: Annotated[Path | None, typer.Option(help="gauntlet.toml.")] = None,
    budget_usd: Annotated[float, typer.Option("--budget-usd", help="Spend cap in USD.")] = 1.0,
    fake_llm: Annotated[Path | None, typer.Option("--fake-llm", hidden=True)] = None,
) -> None:
    """Replay a cassette.

    strict: every effect must be in the cassette; makes no external call. Exit 0 identical,
    1 divergence. agent_live: the recording stands in for the simulator while the agent in
    --target replies as recorded, and everything after the first difference runs live.
    """
    text = _read(file)
    if mode == "strict":
        rep = asyncio.run(replay_strict(text))
        if rep.identical:
            typer.echo(f"identical: {rep.events} events reproduced exactly")
            return
        d = rep.divergence
        assert d is not None
        typer.echo(f"divergence at seq {d.seq}: expected {d.expected!r}, got {d.got!r}")
        raise typer.Exit(1)
    if target is None:
        typer.echo("--mode agent_live needs --target agent.yaml", err=True)
        raise typer.Exit(2)
    try:
        agent = load_agent_file(target)
        cfg = load_config(config)
    except (OSError, ValidationError, ValueError, FileNotFoundError) as e:
        typer.echo(f"{target}:agent_file:{str(e).splitlines()[0]}", err=True)
        raise typer.Exit(2) from e
    _, man = import_cassette(text)
    version = AgentVersion(
        id="agv_replay",
        agent_id="local",
        label=agent.label,
        target=agent.target,
        profile=agent.profile or man.agent_version.profile,  # the recorded policy text
    )
    gateway: Gateway = load_fake_llm(fake_llm) if fake_llm else LiteLLMGateway(cfg)
    store = MemoryJournalStore()
    deps = RunnerDeps(
        store=store,
        gateway=gateway,
        budget=MemoryBudgetLedger(round(budget_usd * 1_000_000)),
        url_policy=UrlPolicy(allow_private=True),
    )
    out, store = asyncio.run(replay_agent_live(text, version, deps, return_store=True))
    events = asyncio.run(store.load("ep_agent_live")).events
    typer.echo(f"outcome: {out.outcome} ({out.termination})")
    live_from = first_live_seq(events)
    typer.echo("no divergence: the agent answered as recorded" if live_from is None
               else f"went live at seq {live_from}")  # fmt: skip
