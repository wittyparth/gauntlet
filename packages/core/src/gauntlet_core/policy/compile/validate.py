"""Code-side validation of proposed rules and rubrics (P4-1). The model proposes, this decides."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError

from gauntlet_core.schema import Policy, PolicyRule, Rubric, ToolSpec
from gauntlet_core.validate import walk_check

from ..engine import validate_policy

__all__ = ["RuleCheck", "check_rubric", "check_rule", "tool_names"]

_HEAD = re.compile(r"^[^.\[]+")


class RuleCheck:
    """Outcome of validating one proposed rule. `repairable` problems (unknown tool or
    argument names) deserve one repair call; the others downgrade the proposal at once."""

    def __init__(
        self,
        rule: PolicyRule | None,
        fatal: list[str] | None = None,
        repairable: list[str] | None = None,
    ) -> None:
        self.rule = rule
        self.fatal = fatal or []
        self.repairable = repairable or []

    @property
    def ok(self) -> bool:
        return self.rule is not None and not self.fatal and not self.repairable

    @property
    def problems(self) -> list[str]:
        return [*self.fatal, *self.repairable]


def tool_names(tools: Sequence[ToolSpec]) -> set[str]:
    return {t.name for t in tools}


def _inventory_problems(rule: PolicyRule, tools: Sequence[ToolSpec]) -> list[str]:
    if not tools:
        return []  # no inventory to check against
    by_name = {t.name: t for t in tools}
    out: list[str] = []
    for node in walk_check(rule.when):
        if node.type not in ("tool_called", "tainted_call") or node.tool == "*":
            continue
        tool = by_name.get(node.tool)
        if tool is None:
            out.append(f"unknown tool {node.tool!r}")
            continue
        props = (tool.input_schema or {}).get("properties", {})
        if node.type == "tool_called" and props:
            for path in node.args:
                m = _HEAD.match(path)
                if m and m.group(0) not in props:
                    out.append(f"tool {node.tool!r} has no argument {m.group(0)!r}")
    return out


def check_rule(raw: Any, tools: Sequence[ToolSpec]) -> RuleCheck:
    try:
        rule = PolicyRule.model_validate(raw)
    except ValidationError as e:
        first = e.errors()[0]
        loc = ".".join(str(x) for x in first["loc"])
        return RuleCheck(None, fatal=[f"invalid rule: {loc}: {first['msg']}"])
    fatal = validate_policy(Policy(id="check", rules=[rule]))
    return RuleCheck(rule, fatal=fatal, repairable=_inventory_problems(rule, tools))


def check_rubric(raw: Any) -> Rubric | None:
    try:
        return Rubric.model_validate(raw)
    except ValidationError:
        return None
