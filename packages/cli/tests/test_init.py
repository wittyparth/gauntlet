from __future__ import annotations

from pathlib import Path

import yaml
from cli_helpers import invoke
from gauntlet_cli.agentfile import AgentFile
from gauntlet_core.llm import load_config


def test_init_writes_valid_files(runner, tmp_path: Path):
    res = invoke(runner, ["init", str(tmp_path)])
    assert res.exit_code == 0
    assert AgentFile.model_validate(yaml.safe_load((tmp_path / "agent.yaml").read_text()))
    cfg = load_config(tmp_path / "gauntlet.toml")
    assert cfg.llm.roles["judge_strong"].model == "openrouter/google/gemini-2.5-flash-lite"
    text = (tmp_path / "agent.yaml").read_text() + (tmp_path / "gauntlet.toml").read_text()
    assert "openai/" not in text and "anthropic/" not in text


def test_init_refuses_to_overwrite_without_force(runner, tmp_path: Path):
    (tmp_path / "agent.yaml").write_text("keep: me\n")
    res = invoke(runner, ["init", str(tmp_path)])
    assert res.exit_code == 2 and "--force" in res.stderr
    assert (tmp_path / "agent.yaml").read_text() == "keep: me\n"
    assert invoke(runner, ["init", str(tmp_path), "--force"]).exit_code == 0
    assert "label:" in (tmp_path / "agent.yaml").read_text()


def test_init_appends_gitignore_once(runner, tmp_path: Path):
    (tmp_path / ".gitignore").write_text("node_modules")
    invoke(runner, ["init", str(tmp_path)])
    invoke(runner, ["init", str(tmp_path), "--force"])
    assert (tmp_path / ".gitignore").read_text().splitlines() == ["node_modules", ".gauntlet/"]


def test_init_does_not_create_gitignore(runner, tmp_path: Path):
    invoke(runner, ["init", str(tmp_path)])
    assert not (tmp_path / ".gitignore").exists()
