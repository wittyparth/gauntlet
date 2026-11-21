"""`gauntlet policy compile` and `gauntlet policy validate` (P4-1)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer
import yaml
from gauntlet_core.llm import Gateway, LiteLLMGateway, load_config
from gauntlet_core.policy import validate_policy
from gauntlet_core.policy.compile import compile_policy
from gauntlet_core.schema import Policy, WorldSpec, dump_yaml, load_yaml
from pydantic import ValidationError

from ..fakellm import load_fake_llm

__all__ = ["policy_app"]

policy_app = typer.Typer(help="Compile and check runtime policies.", no_args_is_help=True)


@policy_app.command("compile")
def compile_cmd(
    file: Annotated[Path | None, typer.Argument(help="Policy text (markdown or plain).")] = None,
    agent_text: Annotated[
        str | None, typer.Option("--agent-text", help="The policy text given inline.")
    ] = None,
    out: Annotated[Path, typer.Option("-o", "--out", help="Policy YAML to write.")] = Path(
        "policy.yaml"
    ),
    tools: Annotated[
        Path | None, typer.Option("--tools", help="A world YAML whose tools are the inventory.")
    ] = None,
    policy_id: Annotated[str, typer.Option("--id", help="Policy id.")] = "policy",
    seed: Annotated[int, typer.Option(help="Seed passed to the model.")] = 0,
    config: Annotated[Path | None, typer.Option(help="gauntlet.toml.")] = None,
    fake_llm: Annotated[Path | None, typer.Option("--fake-llm", hidden=True)] = None,
) -> None:
    """Propose rules for each clause of a policy text.

    Writes OUT (the machine rules, in shadow mode) and OUT.proposals.json (every proposal with
    its class, rationale and confidence). Review both before enforcing anything.
    """
    if (file is None) == (agent_text is None):
        typer.echo("give exactly one of FILE or --agent-text", err=True)
        raise typer.Exit(2)
    try:
        text = file.read_text() if file is not None else str(agent_text)
        inventory = load_yaml(WorldSpec, tools).tools if tools else []
        cfg = load_config(config)
    except (OSError, ValueError, ValidationError, yaml.YAMLError) as e:
        typer.echo(f"cannot load input: {str(e).splitlines()[0]}", err=True)
        raise typer.Exit(2) from e
    gateway: Gateway = load_fake_llm(fake_llm) if fake_llm else LiteLLMGateway(cfg)
    compiled = asyncio.run(
        compile_policy(text, tools=inventory, gateway=gateway, policy_id=policy_id, seed=seed)
    )
    rules = [p.rule for p in compiled.proposals if p.rule is not None]
    policy = Policy(id=policy_id, rules=rules)
    out.write_text(dump_yaml(policy))
    out.with_name(out.name + ".proposals.json").write_text(
        json.dumps(compiled.model_dump(mode="json"), indent=2)
    )
    counts = {
        k: sum(1 for p in compiled.proposals if p.klass == k) for k in ("machine", "model", "human")
    }
    typer.echo(
        f"{len(compiled.clauses)} clauses: {counts['machine']} machine, {counts['model']} model, "
        f"{counts['human']} human; {len(rules)} rules written to {out}; "
        f"cost ${compiled.cost.usd_micros / 1e6:.4f}"
    )
    low = [p.clause_id for p in compiled.proposals if p.low_confidence]
    if low:
        typer.echo(f"low confidence, review: {', '.join(low)}")


@policy_app.command("validate")
def validate_cmd(
    file: Annotated[Path, typer.Argument(help="A policy YAML file.")],
) -> None:
    """Check that a policy loads and every rule can be evaluated before the episode ends.

    Exit 0 valid, 1 problems found, 2 the file cannot be read.
    """
    try:
        policy = load_yaml(Policy, file)
    except (OSError, ValueError, ValidationError, yaml.YAMLError) as e:
        typer.echo(f"{file}: {str(e).splitlines()[0]}", err=True)
        raise typer.Exit(2) from e
    problems = validate_policy(policy)
    for p in problems:
        typer.echo(f"{file}: {p}", err=True)
    if problems:
        raise typer.Exit(1)
    typer.echo(f"{file}: ok ({len(policy.rules)} rules, mode {policy.mode}, fail {policy.fail})")
