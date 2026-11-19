"""`agent.yaml`: `{label, target: <target config>, profile?: <AgentProfile>}`."""

from __future__ import annotations

from pathlib import Path

import yaml
from gauntlet_core.schema import AgentProfile, TargetConfig
from pydantic import BaseModel, ConfigDict

__all__ = ["AgentFile", "load_agent_file"]


class AgentFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    target: TargetConfig
    profile: AgentProfile | None = None


def load_agent_file(path: Path) -> AgentFile:
    return AgentFile.model_validate(yaml.safe_load(Path(path).read_text()))
