"""Rule-level editing of a policy draft (P4-6): add, replace and remove one rule. A rule lives in a
proposal of the draft's compiled policy; publishing builds the next version from accepted ones."""

from __future__ import annotations

from gauntlet_core.policy import validate_policy
from gauntlet_core.policy.compile import CompiledPolicy
from gauntlet_core.policy.compile.clauses import Clause
from gauntlet_core.policy.compile.propose import Proposal
from gauntlet_core.policy.compile.validate import check_rule
from gauntlet_core.schema import Policy, PolicyRule
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import ApiError, not_found
from .audit import audit
from .policies import _editable, dump_doc, sync_draft_doc

__all__ = ["add_rule", "delete_rule", "replace_rule"]

MANUAL = "rule_"  # clause ids of rules added by hand


def _accepted(compiled: CompiledPolicy) -> list[PolicyRule]:
    return [
        p.rule
        for p in compiled.proposals
        if p.rule is not None and p.status in ("accepted", "edited")
    ]


def _validated(raw: PolicyRule, others: list[PolicyRule], policy_id: str) -> PolicyRule:
    res = check_rule(raw.model_dump(mode="json"), [])
    if res.rule is None or res.fatal:
        raise ApiError(422, "validation_error", "invalid rule", res.fatal)
    problems = validate_policy(Policy(id=policy_id, rules=[*others, res.rule]))
    if problems:
        raise ApiError(422, "validation_error", "the rules do not form a valid policy", problems)
    return res.rule


def _find(compiled: CompiledPolicy, rule_id: str) -> Proposal:
    for p in compiled.proposals:
        if p.rule is not None and p.rule.id == rule_id:
            return p
    raise not_found("rule", rule_id)


async def add_rule(
    s: AsyncSession, ws: str, policy_id: str, rule: PolicyRule, actor: str
) -> CompiledPolicy:
    draft, row = await _editable(s, ws, policy_id)
    compiled = CompiledPolicy.model_validate(row.doc)
    if any(p.rule is not None and p.rule.id == rule.id for p in compiled.proposals):
        raise ApiError(409, "rule_exists", f"the policy already has a rule {rule.id!r}")
    ok = _validated(rule, _accepted(compiled), policy_id)
    clause_id = f"{MANUAL}{ok.id}"
    compiled = compiled.model_copy(
        update={
            "clauses": [
                *compiled.clauses,
                Clause(id=clause_id, text=ok.description, source_span=(0, 0)),
            ],
            "proposals": [
                *compiled.proposals,
                Proposal(
                    clause_id=clause_id, clause_text=ok.description, klass="machine", rule=ok,
                    confidence=1.0, rationale="Added by hand.", status="accepted",
                ),
            ],
        }
    )  # fmt: skip
    row.doc = dump_doc(compiled)
    sync_draft_doc(draft, compiled)
    await audit(s, ws, actor, "policy.rule_added", "policy", policy_id,
                {"version": draft.version, "rule_id": ok.id})  # fmt: skip
    await s.commit()
    return compiled


async def replace_rule(
    s: AsyncSession, ws: str, policy_id: str, rule_id: str, rule: PolicyRule, actor: str
) -> CompiledPolicy:
    if rule.id != rule_id:
        raise ApiError(422, "validation_error", "the rule id in the body must match the path")
    draft, row = await _editable(s, ws, policy_id)
    compiled = CompiledPolicy.model_validate(row.doc)
    prop = _find(compiled, rule_id)
    others = [r for r in _accepted(compiled) if r.id != rule_id]
    ok = _validated(rule, others, policy_id)
    new = prop.model_copy(update={"rule": ok, "status": "edited"})
    compiled = compiled.model_copy(
        update={"proposals": [new if p is prop else p for p in compiled.proposals]}
    )
    row.doc = dump_doc(compiled)
    sync_draft_doc(draft, compiled)
    await audit(s, ws, actor, "policy.rule_updated", "policy", policy_id,
                {"version": draft.version, "rule_id": rule_id})  # fmt: skip
    await s.commit()
    return compiled


async def delete_rule(
    s: AsyncSession, ws: str, policy_id: str, rule_id: str, actor: str
) -> CompiledPolicy:
    """A rule added by hand is removed; a compiled one is rejected (its clause stays visible)."""
    draft, row = await _editable(s, ws, policy_id)
    compiled = CompiledPolicy.model_validate(row.doc)
    prop = _find(compiled, rule_id)
    if prop.clause_id.startswith(MANUAL):
        compiled = compiled.model_copy(
            update={
                "clauses": [c for c in compiled.clauses if c.id != prop.clause_id],
                "proposals": [p for p in compiled.proposals if p is not prop],
            }
        )
    else:
        compiled = compiled.model_copy(
            update={
                "proposals": [
                    p.model_copy(update={"status": "rejected"}) if p is prop else p
                    for p in compiled.proposals
                ]
            }
        )
    row.doc = dump_doc(compiled)
    sync_draft_doc(draft, compiled)
    await audit(s, ws, actor, "policy.rule_deleted", "policy", policy_id,
                {"version": draft.version, "rule_id": rule_id})  # fmt: skip
    await s.commit()
    return compiled
