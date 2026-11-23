"""Generated references equal the committed ones; the site builds strictly; quickstart runs."""

from __future__ import annotations

import subprocess
import sys

import pytest

from tools.docs import api_ref, check_ref, cli_ref, quickstart_check
from tools.docs._common import OUT, ROOT


@pytest.mark.parametrize("gen", [cli_ref, api_ref, check_ref])
def test_generated_reference_is_current(gen):
    for name, text in gen.render().items():
        assert (OUT / name).read_text() == text, (
            f"{name} is stale: run `uv run python -m {gen.__name__}`"
        )


def test_quickstart_blocks_are_found():
    assert len(quickstart_check.commands(quickstart_check.QUICKSTART.read_text())) == 4


def test_quickstart_runs_green_on_the_scripted_example():
    assert quickstart_check.main() == 0


def test_mkdocs_builds_strict(tmp_path):
    res = subprocess.run(
        [sys.executable, "-m", "mkdocs", "build", "--strict", "-d", str(tmp_path / "site")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={"NO_MKDOCS_2_WARNING": "1", "PATH": "/usr/bin:/bin"},
    )
    assert res.returncode == 0, res.stderr[-1500:]
