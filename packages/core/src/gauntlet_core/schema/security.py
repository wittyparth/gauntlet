"""Attacks and findings (contracts section 6)."""

from __future__ import annotations

from typing import Literal

from .authoring import Scenario
from .checks import Check
from .common import Model, Severity
from .policy import PolicyRule

Vector = Literal["user_turn", "document", "tool_result", "tool_description", "system_context"]
FindingStatus = Literal[
    "open", "triaged", "in_progress", "fixed", "verified", "accepted_risk", "false_positive"
]


class Attack(Model):
    id: str
    title: str
    category: str
    technique: str
    source: str
    license: str
    vector: Vector
    payload: str | list[str]  # list = multi-turn; supports {{marker}} and {{canary:<id>}}
    objective: Check
    requires: list[str] = []
    severity: Severity = "high"
    target: str | None = None  # document id or tool name the payload is placed in


class Finding(Model):
    id: str
    title: str
    category: str
    severity: Severity
    agent_version_id: str
    attack_id: str | None = None
    episode_ids: list[str] = []
    reproducibility: tuple[int, int] = (0, 0)  # successes, attempts
    reproducer: Scenario
    status: FindingStatus = "open"
    root_cause_hint: str | None = None
    suggested_policy: PolicyRule | None = None
    dedup_key: str = ""
