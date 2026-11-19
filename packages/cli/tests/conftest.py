from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pytest
from cli_helpers import FIXTURES
from gauntlet_cli.fakellm import ScriptedLLM
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def pack() -> Path:
    return FIXTURES / "tinyshop"


@pytest.fixture
def smoke_args(pack: Path, tmp_path: Path) -> list[str]:
    return [
        "run",
        str(pack),
        "--target",
        str(FIXTURES / "agent.yaml"),
        "--suite",
        "smoke",
        "--fake-llm",
        str(FIXTURES / "fake_llm_smoke.yaml"),
        "--out",
        str(tmp_path / "run"),
    ]


@pytest.fixture
def llm_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every call that reaches the (scripted) gateway, by role."""
    calls: list[str] = []
    original = ScriptedLLM.complete

    async def counting(self, role, messages, **kw):  # type: ignore[no-untyped-def]
        calls.append(role)
        return await original(self, role, messages, **kw)

    monkeypatch.setattr(ScriptedLLM, "complete", counting)
    return calls
