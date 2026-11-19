"""`gauntlet init`."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
FILES = ("gauntlet.toml", "agent.yaml")


def init(
    directory: Annotated[Path, typer.Argument(help="Target directory.")] = Path("."),
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing files.")] = False,
) -> None:
    """Write gauntlet.toml and a hosted agent.yaml template."""
    directory.mkdir(parents=True, exist_ok=True)
    existing = [f for f in FILES if (directory / f).exists()]
    if existing and not force:
        typer.echo(f"refusing to overwrite {', '.join(existing)} (use --force)", err=True)
        raise typer.Exit(2)
    for f in FILES:
        (directory / f).write_text((TEMPLATES / f).read_text())
        typer.echo(f"wrote {directory / f}")
    gitignore = directory / ".gitignore"
    if gitignore.exists() and ".gauntlet/" not in gitignore.read_text().splitlines():
        text = gitignore.read_text()
        gitignore.write_text(
            text + ("" if text.endswith("\n") or not text else "\n") + ".gauntlet/\n"
        )
        typer.echo("added .gauntlet/ to .gitignore")
