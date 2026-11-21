"""Runtime policy enforcement (hard-cores 7.1, CQ-G1, CQ-G4). Pure and synchronous."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any, Literal

from gauntlet_core.checks import NotPrefixEvaluable, assert_prefix_evaluable
from gauntlet_core.checks import names as detector_names
from gauntlet_core.checks.context import Ctx, PrefixView, ProposedAction, ctx_from_prefix
from gauntlet_core.checks.registry import eval_node
from gauntlet_core.schema import SEVERITY_ORDER, Evidence, Json, Model, Policy, PolicyRule
from gauntlet_core.validate import walk_check

__all__ = ["GatewayDecision", "PolicyEngine", "validate_policy"]

DecisionAction = Literal["allow", "block", "require_approval", "redact", "log"]
_ACTION_RANK = {"block": 3, "require_approval": 2, "redact": 1, "log": 0}
_MARKER_NOTE = re.compile(r"taint marker '([^']+)'")


class GatewayDecision(Model):
    action: DecisionAction
    rule_id: str | None = None
    message: str | None = None
    evidence: list[Evidence] = []
    modified: Json | None = None
    undetermined: list[str] = []


def validate_policy(policy: Policy, *, registry: Mapping[str, Any] | None = None) -> list[str]:
    """Problems that make a policy unloadable: duplicate ids, rules needing the whole
    trajectory (`judge`, `state_diff`), unknown detectors. Empty list = valid."""
    known = set(registry) if registry is not None else set(detector_names())
    problems: list[str] = []
    seen: set[str] = set()
    for rule in policy.rules:
        if rule.id in seen:
            problems.append(f"{rule.id}: duplicate rule id")
        seen.add(rule.id)
        try:
            assert_prefix_evaluable(rule.when)
        except NotPrefixEvaluable as exc:
            problems.append(f"{rule.id}: {exc}")
        for node in walk_check(rule.when):
            if node.type == "detector" and node.name not in known:
                problems.append(f"{rule.id}: unknown detector {node.name!r}")
    return problems


class PolicyEngine:
    """`registry` (detector name -> fn) is used to validate detector names; evaluation uses the
    process-wide detector registry."""

    def __init__(self, policy: Policy, *, registry: Mapping[str, Any] | None = None) -> None:
        problems = validate_policy(policy, registry=registry)
        if problems:
            raise ValueError("invalid policy: " + "; ".join(problems))
        self.policy = policy

    def decide(self, prefix: PrefixView, proposed: ProposedAction) -> GatewayDecision:
        ctx = ctx_from_prefix(prefix, proposed)
        undetermined: list[str] = []
        best: tuple[PolicyRule, list[Evidence]] | None = None
        best_key: tuple[int, int, int] = (-1, -1, 0)
        for idx, rule in enumerate(self.policy.rules):
            res = eval_node(rule.when, ctx)
            if res.tri is True and res.stable:
                seq = ctx.proposed_seq
                if res.evidence and seq is not None and max(e.seq for e in res.evidence) < seq:
                    continue  # already held before this action; it was decided then
                hit: PolicyRule = rule
                evidence = res.evidence
            elif res.tri is False:
                continue
            else:
                undetermined.append(rule.id)
                if not (rule.strict and self.policy.fail == "closed"):
                    continue
                hit = rule.model_copy(
                    update={
                        "action": "block",
                        "message": rule.message or f"{rule.id}: undetermined, failing closed",
                    }
                )
                evidence = []
            key = (SEVERITY_ORDER[hit.severity], _ACTION_RANK[hit.action], -idx)
            if key > best_key:
                best, best_key = (hit, evidence), key
        if best is None:
            return GatewayDecision(action="allow", undetermined=undetermined)
        rule, evidence = best
        message = rule.message or rule.description
        if rule.action == "redact":
            modified = _redact(rule, ctx, proposed)
            if modified is None:
                message = f"{message} (no span to redact; blocked)"
                return GatewayDecision(
                    action="block",
                    rule_id=rule.id,
                    message=message,
                    evidence=evidence,
                    undetermined=undetermined,
                )
            return GatewayDecision(
                action="redact",
                rule_id=rule.id,
                message=message,
                evidence=evidence,
                modified=modified,
                undetermined=undetermined,
            )
        return GatewayDecision(
            action=rule.action,
            rule_id=rule.id,
            message=message,
            evidence=evidence,
            undetermined=undetermined,
        )


# -- redaction ----------------------------------------------------------------------------


def _spans(rule: PolicyRule, ctx: Ctx, proposed: ProposedAction, texts: list[str]) -> list[str]:
    """Literal strings the rule matched, as far as we can locate them in the proposed payload."""
    joined = "\n".join(texts)
    found: list[str] = []
    res = eval_node(rule.when, ctx)
    for ev in res.evidence:
        if ev.seq != ctx.proposed_seq:
            continue
        whole = (joined, json.dumps(proposed.args, sort_keys=True))
        if (
            ev.quote
            and not ev.quote.endswith("...")
            and ev.quote in joined
            and ev.quote not in whole
        ):
            found.append(ev.quote)
        m = _MARKER_NOTE.search(ev.note or "")
        if m and m.group(1) in joined:
            found.append(m.group(1))
    for c in ctx.canaries:
        for v in {c.value, *c.variants}:
            if v and v.lower() in joined.lower():
                found.extend(
                    mm.group(0) for mm in re.finditer(re.escape(v), joined, flags=re.IGNORECASE)
                )
    for e in ctx.events:
        for mk in e.origin.markers if e.origin else []:
            if mk and mk in joined:
                found.append(mk)
    for node in walk_check(rule.when):
        matchers = []
        if node.type == "output":
            matchers = [node.matcher]
        elif node.type == "tool_called":
            matchers = list(node.args.values())
        for mt in matchers:
            if mt.regex:
                found.extend(mm.group(0) for mm in re.finditer(mt.regex, joined) if mm.group(0))
    return sorted({s for s in found if s}, key=len, reverse=True)


def _sub(value: Any, spans: list[str], token: str) -> tuple[Any, bool]:
    if isinstance(value, str):
        out = value
        for s in spans:
            out = re.sub(re.escape(s), token, out, flags=re.IGNORECASE)
        return out, out != value
    if isinstance(value, dict):
        changed = False
        d: dict[str, Any] = {}
        for k, v in value.items():
            d[k], c = _sub(v, spans, token)
            changed = changed or c
        return d, changed
    if isinstance(value, list):
        items = [_sub(v, spans, token) for v in value]
        return [i for i, _ in items], any(c for _, c in items)
    return value, False


def _strings(v: Any) -> list[str]:
    if isinstance(v, str):
        return [v]
    if isinstance(v, dict):
        return [s for x in v.values() for s in _strings(x)]
    if isinstance(v, list):
        return [s for x in v for s in _strings(x)]
    return []


def _redact(rule: PolicyRule, ctx: Ctx, proposed: ProposedAction) -> Json | None:
    """The rewritten payload, or None when no span could be located (caller escalates)."""
    token = f"[REDACTED:{rule.id}]"
    if proposed.kind == "agent_message":
        spans = _spans(rule, ctx, proposed, [proposed.text or ""])
        text, changed = _sub(proposed.text or "", spans, token)
        return {"text": text} if changed else None
    spans = _spans(rule, ctx, proposed, _strings(proposed.args))
    args, changed = _sub(proposed.args, spans, token)
    return {"tool": proposed.tool, "args": args} if changed else None
