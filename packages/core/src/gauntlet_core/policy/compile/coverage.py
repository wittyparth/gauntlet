"""Coverage of a compiled policy (P4-1): which clauses are enforced, which rules were ever
exercised by a stored trajectory, which are risky for benign traffic."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from gauntlet_core.checks import evaluate_prefix, prefix_from_events, proposed_from_event
from gauntlet_core.schema import Model, Policy, PolicyRule, Trajectory

from ..offline import _classify, test_policy
from .propose import CompiledPolicy, Proposal

__all__ = [
    "FP_THRESHOLD",
    "ClauseCoverage",
    "CoverageReport",
    "RuleCoverage",
    "accepted_proposals",
    "accepted_rules",
    "coverage_report",
]

FP_THRESHOLD = 0.05


class ClauseCoverage(Model):
    clause_id: str
    text: str
    klass: Literal["machine", "model", "human"] | None = None
    status: str | None = None
    rule_id: str | None = None


class RuleCoverage(Model):
    rule_id: str
    attack_hits: int = 0
    benign_hits: int = 0
    benign_total: int = 0
    high_false_positive_risk: bool = False


class CoverageReport(Model):
    clauses_total: int
    machine: int
    model: int
    human: int
    uncovered: list[str]
    rules_exercised: list[RuleCoverage]
    rules_untested: list[str]
    by_clause: list[ClauseCoverage]
    trajectories: int = 0


def accepted_proposals(compiled: CompiledPolicy) -> list[Proposal]:
    return [p for p in compiled.proposals if p.status in ("accepted", "edited")]


def accepted_rules(compiled: CompiledPolicy) -> list[PolicyRule]:
    return [p.rule for p in accepted_proposals(compiled) if p.rule is not None]


def _activity(rule: PolicyRule, traj: Trajectory) -> tuple[bool, bool]:
    """(evaluated, violates): did any agent action get a violates-or-ok answer, and a violation."""
    evaluated = violates = False
    seen: list = []
    for e in traj.events:
        if e.actor == "agent" and e.kind in ("tool_call", "agent_message"):
            prefix = prefix_from_events(
                seen,
                initial_world=traj.initial_world or None,
                canaries=traj.canaries,
                tool_risk=traj.tool_risk,
                honeytools=traj.honeytools,
            )
            d = evaluate_prefix(rule.when, prefix, proposed_from_event(e))
            if d != "undetermined":
                evaluated = True
            if d == "violates":
                violates = True
        seen.append(e)
    return evaluated, violates


def coverage_report(
    compiled: CompiledPolicy, trajectories: Sequence[Trajectory] | None = None
) -> CoverageReport:
    props = compiled.proposals
    accepted = accepted_proposals(compiled)
    covered = {p.clause_id for p in accepted if p.rule is not None or p.rubric is not None}
    by_clause: list[ClauseCoverage] = []
    by_id = {p.clause_id: p for p in props}
    for c in compiled.clauses:
        p = by_id.get(c.id)
        by_clause.append(
            ClauseCoverage(
                clause_id=c.id,
                text=c.text,
                klass=p.klass if p else None,
                status=p.status if p else None,
                rule_id=p.rule.id if p and p.rule else None,
            )
        )
    uncovered = [c.id for c in compiled.clauses if c.id not in covered]
    exercised: list[RuleCoverage] = []
    untested: list[str] = []
    trajs = list(trajectories or [])
    rules = accepted_rules(compiled)
    if trajs and rules:
        kinds = [_classify(t) for t in trajs]
        n_benign = sum(1 for k, _ in kinds if k == "benign")
        fp = {
            s.rule_id: s.false_positives
            for s in test_policy(Policy(id=compiled.policy_id, rules=rules), trajs).per_rule
        }
        for rule in rules:
            ev_any = False
            attack = benign = 0
            for t, (kind, _) in zip(trajs, kinds, strict=True):
                evaluated, violates = _activity(rule, t)
                ev_any = ev_any or evaluated
                if violates and kind == "attack":
                    attack += 1
                elif violates and kind == "benign":
                    benign += 1
            if not ev_any:
                untested.append(rule.id)
                continue
            exercised.append(
                RuleCoverage(
                    rule_id=rule.id,
                    attack_hits=attack,
                    benign_hits=benign,
                    benign_total=n_benign,
                    high_false_positive_risk=bool(
                        n_benign and fp.get(rule.id, 0) / n_benign > FP_THRESHOLD
                    ),
                )
            )
    else:
        untested = [r.id for r in rules]
    return CoverageReport(
        clauses_total=len(compiled.clauses),
        machine=sum(1 for p in props if p.klass == "machine"),
        model=sum(1 for p in props if p.klass == "model"),
        human=sum(1 for p in props if p.klass == "human"),
        uncovered=uncovered,
        rules_exercised=exercised,
        rules_untested=untested,
        by_clause=by_clause,
        trajectories=len(trajs),
    )
