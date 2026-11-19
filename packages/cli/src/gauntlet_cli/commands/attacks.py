"""`gauntlet attacks`: browse and validate the attack library."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from gauntlet_core.security import (
    DEFAULT_TAXONOMY_PATH,
    AttackLibrary,
    Issue,
    load_attacks,
    load_taxonomy,
    payload_texts,
)

__all__ = ["attacks_app"]

attacks_app = typer.Typer(help="Browse and validate the attack library.", no_args_is_help=True)
DEFAULT_ROOT = DEFAULT_TAXONOMY_PATH.parent / "library"
RootArg = Annotated[Path, typer.Argument(help="Library root (attacks/library).")]


def _load(root: Path) -> tuple[AttackLibrary, list[Issue]]:
    lib = load_attacks(root, load_taxonomy())
    return lib, list(lib.issues)


def _notice_issues(lib: AttackLibrary, root: Path) -> list[Issue]:
    """Every attack's source project must have an entry in NOTICES.md (when one exists)."""
    notices = root.parent / "NOTICES.md"
    if not notices.is_file():
        return []
    text = notices.read_text()
    out = []
    for project in sorted({a.source.split("@", 1)[0] for a in lib.attacks}):
        if project not in text:
            out.append(Issue("missing_notice", f"no NOTICES.md entry for {project!r}"))
    return out


@attacks_app.command("list")
def list_cmd(
    root: Annotated[Path, typer.Option("--root")] = DEFAULT_ROOT,
    category: Annotated[str | None, typer.Option()] = None,
    source: Annotated[str | None, typer.Option()] = None,
    vector: Annotated[str | None, typer.Option()] = None,
    q: Annotated[str | None, typer.Option()] = None,
    fmt: Annotated[str, typer.Option("--format")] = "text",
) -> None:
    """List attacks, optionally filtered."""
    lib, _ = _load(root)
    found = lib.filter(category=category, vector=vector, source=source, q=q)
    if fmt == "json":
        typer.echo(json.dumps([a.model_dump(mode="json") for a in found], indent=2))
        return
    for a in found:
        typer.echo(f"{a.id}\t{a.category}\t{a.vector}\t{a.severity}\t{a.source}")


@attacks_app.command("show")
def show(
    attack_id: str,
    root: Annotated[Path, typer.Option("--root")] = DEFAULT_ROOT,
    fmt: Annotated[str, typer.Option("--format")] = "text",
) -> None:
    """Show one attack."""
    lib, _ = _load(root)
    a = lib.get(attack_id)
    if a is None:
        typer.echo(f"no attack {attack_id!r}", err=True)
        raise typer.Exit(2)
    if fmt == "json":
        typer.echo(json.dumps(a.model_dump(mode="json"), indent=2))
        return
    typer.echo(f"{a.id}: {a.title}")
    for k in ("category", "vector", "severity", "technique", "source", "license"):
        typer.echo(f"  {k}: {getattr(a, k)}")
    typer.echo(f"  requires: {', '.join(a.requires) or '-'}")
    for i, t in enumerate(payload_texts(a), 1):
        typer.echo(f"  payload[{i}]: {t}")


@attacks_app.command("stats")
def stats(root: Annotated[Path, typer.Option("--root")] = DEFAULT_ROOT) -> None:
    """Counts by category and vector."""
    lib, _ = _load(root)
    for cat, row in sorted(lib.stats().items()):
        total = sum(row.values())
        detail = ", ".join(f"{v}={n}" for v, n in sorted(row.items()))
        typer.echo(f"{cat}\t{total}\t{detail}")
    typer.echo(f"total\t{len(lib.attacks)}")


def _validate(root: Path) -> None:
    lib, issues = _load(root)
    issues += _notice_issues(lib, root)
    for i in issues:
        typer.echo(str(i))
    raise typer.Exit(1 if issues else 0)


@attacks_app.command("validate")
def validate_cmd(root: RootArg = DEFAULT_ROOT) -> None:
    """Validate every attack (exit 0 clean, 1 issues)."""
    _validate(root)


@attacks_app.command("verify", hidden=True)
def verify_cmd(root: RootArg = DEFAULT_ROOT) -> None:
    """Alias of `validate` (name used in the plan)."""
    _validate(root)
