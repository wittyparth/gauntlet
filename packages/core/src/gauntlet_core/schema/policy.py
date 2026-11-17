"""Runtime policies (contracts section 7)."""

from __future__ import annotations

from typing import Literal

from .checks import Check
from .common import Model, Severity

PolicyAction = Literal["block", "require_approval", "redact", "log"]


class PolicyRule(Model):
    id: str
    description: str
    severity: Severity = "high"
    when: Check
    action: PolicyAction = "block"
    message: str | None = None
    strict: bool = False  # an undetermined result follows the policy's fail mode


class Policy(Model):
    id: str
    version: int = 1
    rules: list[PolicyRule]
    mode: Literal["shadow", "enforce"] = "shadow"
    fail: Literal["open", "closed"] = "open"
