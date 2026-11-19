"""`gauntlet lint`: static checks for agent code and configs (Python, YAML, JSON)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from gauntlet_core.security.scan import SEVERITY_RANK, exceeds, lint_paths, render

__all__ = ["lint"]


def _ids(raw: str | None) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()] if raw else []


def lint(
    paths: Annotated[list[Path], typer.Argument(help="Files or directories.")],
    fmt: Annotated[str, typer.Option("--format", help="text, json or sarif.")] = "text",
    fail_on: Annotated[str, typer.Option(help="low, medium, high or critical.")] = "high",
    select: Annotated[
        str | None, typer.Option(help="Only these rule ids (comma separated).")
    ] = None,
    ignore: Annotated[str | None, typer.Option(help="Skip these rule ids.")] = None,
) -> None:
    """Lint agent code (exit 0 clean, 1 findings at or above --fail-on, 2 usage error)."""
    if fail_on not in SEVERITY_RANK or fmt not in {"text", "json", "sarif"}:
        typer.echo("bad --fail-on or --format", err=True)
        raise typer.Exit(2)
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        typer.echo(f"no such path: {', '.join(missing)}", err=True)
        raise typer.Exit(2)
    findings = lint_paths(paths, select=_ids(select), ignore=_ids(ignore))
    out = render(findings, fmt, tool="gauntlet-lint")
    if out:
        typer.echo(out)
    raise typer.Exit(1 if exceeds(findings, fail_on) else 0)
