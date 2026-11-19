"""The `gauntlet` command."""

from __future__ import annotations

import typer

from .commands.demo import demo_app
from .commands.init import init
from .commands.report import report
from .commands.run import run
from .commands.validate import validate

__all__ = ["app"]

app = typer.Typer(
    name="gauntlet",
    help="Simulate, record and evaluate AI agents in a mock world.",
    no_args_is_help=True,
    add_completion=False,
)
app.command()(init)
app.command()(validate)
app.command()(run)
app.command()(report)
app.add_typer(demo_app, name="demo")

if __name__ == "__main__":  # pragma: no cover
    app()
