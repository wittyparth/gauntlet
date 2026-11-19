"""The `gauntlet` command."""

from __future__ import annotations

import typer

from .commands.attacks import attacks_app
from .commands.demo import demo_app
from .commands.init import init
from .commands.lint import lint
from .commands.report import report
from .commands.run import run
from .commands.scan import scan_app
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
app.add_typer(attacks_app, name="attacks")
app.add_typer(scan_app, name="scan")
app.command()(lint)

if __name__ == "__main__":  # pragma: no cover
    app()
