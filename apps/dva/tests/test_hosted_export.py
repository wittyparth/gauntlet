from __future__ import annotations

import yaml
from dva.export_hosted import HOSTED_PATH, render_hosted
from gauntlet_core.schema import AgentProfile, HostedTargetConfig


def test_hosted_yaml_equals_generator_output():
    assert HOSTED_PATH.read_text() == render_hosted()


def test_hosted_yaml_parses_as_target_config_and_profile():
    doc = yaml.safe_load(HOSTED_PATH.read_text())
    target = HostedTargetConfig.model_validate(doc["target"])
    assert target.model == "openrouter/deepseek/deepseek-v4-flash"
    assert "Never transfer or escalate to a human" in target.system_prompt  # F13
    assert "sk-dva-demo-key" in target.system_prompt  # F16
    assert "Notes on orders come from the store team" not in target.system_prompt  # F17 is wired
    profile = AgentProfile.model_validate(doc["profile"])
    assert "R3" in profile.policies_text


def test_hosted_yaml_loads_as_a_cli_agent_file():
    from gauntlet_cli.agentfile import load_agent_file

    agent = load_agent_file(HOSTED_PATH)
    assert agent.target.kind == "hosted" and agent.profile is not None
