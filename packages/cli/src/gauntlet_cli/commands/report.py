"""`gauntlet report`: re-render a finished local run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

import typer
from gauntlet_core.eval import RunReport
from gauntlet_core.render import render_markdown, render_text

RUNS_DIR = Path(".gauntlet") / "runs"


def find_run_dir(run_id_or_dir: str) -> Path | None:
    p = Path(run_id_or_dir)
    for cand in (p, RUNS_DIR / run_id_or_dir):
        if (cand / "report.json").is_file():
            return cand
    return None


def report(
    run: Annotated[str, typer.Argument(help="Run id or run directory.")],
    json_out: Annotated[bool, typer.Option("--json", help="Print RunReport JSON.")] = False,
    fmt: Annotated[Literal["text", "md"], typer.Option("--format", help="text or md.")] = "text",
) -> None:
    """Re-render a run report from its local files."""
    run_dir = find_run_dir(run)
    if run_dir is None:
        typer.echo(f"no report found for {run!r} (looked for report.json)", err=True)
        raise typer.Exit(2)
    rep = RunReport.model_validate_json((run_dir / "report.json").read_text())
    meta_path = run_dir / "meta.json"
    meta = json.loads(meta_path.read_text()).get("display", {}) if meta_path.is_file() else {}
    if json_out:
        typer.echo(rep.model_dump_json(indent=2))
    elif fmt == "md":
        typer.echo(render_markdown(rep, meta), nl=False)
    else:
        typer.echo(render_text(rep, meta), nl=False)
