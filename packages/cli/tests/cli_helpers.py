from __future__ import annotations

from pathlib import Path

from gauntlet_cli.main import app
from typer.testing import CliRunner

FIXTURES = Path(__file__).parent / "fixtures"


def invoke(runner: CliRunner, args: list[str]):  # type: ignore[no-untyped-def]
    return runner.invoke(app, args)
