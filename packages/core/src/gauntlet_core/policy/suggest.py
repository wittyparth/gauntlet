"""From finding to rule (hard-cores 7.3): template-based on the objective type. A model may
write the description later; nothing here calls one."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from gauntlet_core.schema import SEVERITY_ORDER, Finding, PolicyRule, WorldSpec
from gauntlet_core.validate import walk_check

__all__ = ["suggest_rule"]

_PRIORITY = ["tainted_call", "canary_leaked", "egress", "tool_called", "detector", "output"]


def _objective(finding: Finding) -> Any:
    forb = finding.reproducer.forbidden
    named = next((f for f in forb if f.id == "objective"), None)
    if named is None and forb:
        named = max(forb, key=lambda f: SEVERITY_ORDER[f.severity])
    if named is None:
        raise ValueError(f"finding {finding.id} has no objective check to turn into a rule")
    return named.check


def _leaf(check: Any) -> Any:
    leaves = [n for n in walk_check(check) if n.type in _PRIORITY]
    if not leaves:
        raise ValueError("objective has no node a rule can be built from")
    return min(leaves, key=lambda n: _PRIORITY.index(n.type))


def _honeytools(finding: Finding) -> set[str]:
    w = finding.reproducer.world
    return {t.name for t in w.tools if t.honeytool} if isinstance(w, WorldSpec) else set()


def suggest_rule(finding: Finding) -> PolicyRule:
    leaf = _leaf(_objective(finding))
    digest = hashlib.sha256(
        json.dumps(leaf.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()[:8]
    rid = f"suggested-{finding.category}-{digest}"
    sev = finding.severity
    if leaf.type == "tainted_call":
        tool = leaf.tool
        soft = SEVERITY_ORDER[sev] < SEVERITY_ORDER["high"]
        return PolicyRule(
            id=rid,
            description=f"Do not let {tool if tool != '*' else 'a tool'} act on untrusted content",
            severity=sev,
            when=leaf,
            action="require_approval" if soft else "block",
            message="Blocked: this tool call carries content from an untrusted source.",
        )
    if leaf.type == "tool_called":
        if leaf.tool in _honeytools(finding):
            return PolicyRule(
                id=rid,
                description=f"Deny the honeytool {leaf.tool}; no legitimate task uses it",
                severity=sev,
                when=leaf.model_copy(update={"args": {}}),
                action="block",
                message=f"{leaf.tool} is not available.",
            )
        what = "with these arguments" if leaf.args else "at all"
        return PolicyRule(
            id=rid,
            description=f"Constrain {leaf.tool}: block calls {what}",
            severity=sev,
            when=leaf,
            action="block",
            message=f"Blocked: {leaf.tool} may not be called {what}.",
        )
    if leaf.type == "canary_leaked":
        return PolicyRule(
            id=rid,
            description="Redact protected values from agent output and tool arguments",
            severity=sev,
            when=leaf,
            action="redact",
            message="Protected data was removed.",
        )
    if leaf.type == "egress":
        return PolicyRule(
            id=rid,
            description="Only allow the listed domains and recipients",
            severity=sev,
            when=leaf,
            action="redact",
            message="An address outside the allowlist was removed.",
        )
    return PolicyRule(
        id=rid,
        description=f"Block when {leaf.type} objective matches",
        severity=sev,
        when=leaf,
        action="block",
        message="Blocked by policy.",
    )
