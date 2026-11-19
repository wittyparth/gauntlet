from pathlib import Path

import pytest
from gauntlet_core.llm import load_config
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[4]


def test_defaults_load_without_a_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GAUNTLET_CONFIG", raising=False)
    c = load_config()
    assert c.llm.roles["judge_small"].model == "openrouter/qwen/qwen3.7-flash"
    assert c.llm.roles["judge_strong"].model == "openrouter/z-ai/glm-5.3-flash"
    assert c.llm.roles["attacker"].model == "openrouter/deepseek/deepseek-v4-flash"
    assert c.llm.roles["simulator"].temperature == 0.7
    assert all(not r.model.startswith(("openai/", "anthropic/")) for r in c.llm.roles.values())


def test_env_interpolation(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_MODEL", "openrouter/x/y")
    f = tmp_path / "g.toml"
    f.write_text('[llm.roles.simulator]\nmodel = "${MY_MODEL}"\n')
    c = load_config(f)
    assert c.llm.roles["simulator"].model == "openrouter/x/y"
    assert "judge_small" in c.llm.roles  # merged over defaults


def test_missing_env_names_the_variable(tmp_path, monkeypatch):
    monkeypatch.delenv("NOPE_VAR", raising=False)
    f = tmp_path / "g.toml"
    f.write_text('[llm.roles.simulator]\nmodel = "${NOPE_VAR}"\n')
    with pytest.raises(ValueError, match="NOPE_VAR"):
        load_config(f)


def test_unknown_key_rejected(tmp_path):
    f = tmp_path / "g.toml"
    f.write_text("[llm]\nbogus = 1\n")
    with pytest.raises(ValidationError):
        load_config(f)


def test_example_parses():
    c = load_config(ROOT / "gauntlet.example.toml")
    assert c.llm.rate_limits["openrouter"].rpm == 60
    assert c.llm.pricing["openrouter/qwen/qwen3.7-flash"].input_per_mtok == 30_000
