"""Compile a policy text into reviewable proposals (P4-1). One structured model call per batch
of 8 clauses; code validates every proposal and downgrades what cannot be enforced."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel

from gauntlet_core.llm import Gateway, GatewayError, LLMResult
from gauntlet_core.llm.structured import repair_messages as llm_repair_messages
from gauntlet_core.llm.types import StructuredOutputError
from gauntlet_core.schema import Cost, Json, Model, PolicyRule, Rubric, ToolSpec

from .clauses import Clause, split_clauses
from .prompts import PROMPT_VERSION, batch_messages, repair_messages, rubric_messages
from .validate import check_rubric, check_rule

__all__ = [
    "BATCH_SIZE",
    "CompiledPolicy",
    "Proposal",
    "ProposalBatch",
    "ProposalDraft",
    "compile_policy",
    "default_action",
    "default_severity",
]

BATCH_SIZE = 8
LOW_CONFIDENCE = 0.6
Klass = Literal["machine", "model", "human"]
Status = Literal["proposed", "accepted", "rejected", "edited"]

_HARD = re.compile(r"\b(never|must not|mustn't|prohibited|forbidden|do not|don't|cannot)\b", re.I)
_SOFT = re.compile(r"\bshould\b", re.I)
_APPROVAL = re.compile(r"\b(approv\w*|escalat\w*|supervisor|human)\b", re.I)


class ProposalDraft(BaseModel):
    """What the model returns per clause. Rule and rubric stay raw: code validates them."""

    clause_id: str
    klass: Klass
    rule: dict[str, Any] | None = None
    rubric: dict[str, Any] | None = None
    confidence: float = 0.5
    rationale: str = ""


class ProposalBatch(BaseModel):
    items: list[ProposalDraft]


class Proposal(Model):
    clause_id: str
    clause_text: str
    klass: Klass
    rule: PolicyRule | None = None
    rubric: Rubric | None = None
    confidence: float
    rationale: str
    status: Status = "proposed"

    @property
    def low_confidence(self) -> bool:
        return self.confidence < LOW_CONFIDENCE


class CompiledPolicy(Model):
    policy_id: str
    clauses: list[Clause]
    proposals: list[Proposal]
    cost: Cost = Cost()
    prompt_version: str = PROMPT_VERSION


def default_severity(text: str) -> Literal["medium", "high"]:
    return "high" if _HARD.search(text) else "medium"


def default_action(text: str) -> Literal["block", "require_approval", "log"] | None:
    """Keyword default; None when the clause gives no signal (keep the model's choice)."""
    if _APPROVAL.search(text):
        return "require_approval"
    if _HARD.search(text):
        return "block"
    if _SOFT.search(text):
        return "log"
    return None


class _Meter:
    def __init__(self, gateway: Gateway, seed: int) -> None:
        self.gateway, self.seed = gateway, seed
        self.cost = Cost()

    async def ask(
        self, messages: list[Json], model: type[BaseModel], *, attempts: int = 1
    ) -> BaseModel | None:
        """Structured call with temperature 0. On invalid output, one repair retry when
        `attempts` > 1. Returns None when the model never produced a valid object."""
        msgs = messages
        for i in range(attempts):
            try:
                res: LLMResult = await self.gateway.complete(
                    "generator",
                    msgs,
                    response_model=model,
                    temperature=0.0,
                    seed=self.seed,
                )
            except StructuredOutputError as e:
                msgs = llm_repair_messages(messages, e.raw_text, e.message)
                if i + 1 == attempts:
                    return None
                continue
            except GatewayError:
                return None
            self.cost = self.cost + res.cost
            return res.parsed if isinstance(res.parsed, model) else None
        return None


def _unique_rule_id(rule: PolicyRule, clause: Clause, used: set[str]) -> PolicyRule:
    rid = rule.id
    if rid in used:
        rid = f"{rule.id}-{clause.id}"
    used.add(rid)
    return rule if rid == rule.id else rule.model_copy(update={"id": rid})


def _apply_defaults(rule: PolicyRule, clause: Clause, klass: Klass) -> PolicyRule:
    update: dict[str, Any] = {"severity": default_severity(clause.text)}
    action = "require_approval" if klass == "human" else default_action(clause.text)
    if action is not None:
        update["action"] = action
    if not rule.message:
        update["message"] = f"Blocked by policy: {rule.description}"
    return rule.model_copy(update=update)


async def _rubric_for(
    clause: Clause, draft_rubric: Any, policy_id: str, meter: _Meter
) -> Rubric | None:
    rubric = check_rubric(draft_rubric) if draft_rubric else None
    if rubric is None:
        got = await meter.ask(rubric_messages(clause, policy_id), Rubric)
        rubric = got if isinstance(got, Rubric) else None
    if rubric is None:
        return None
    rid = f"{policy_id}-{clause.id}"
    return rubric.model_copy(update={"id": rid})


async def _resolve(
    draft: ProposalDraft,
    clause: Clause,
    tools: Sequence[ToolSpec],
    policy_id: str,
    meter: _Meter,
    used_ids: set[str],
) -> Proposal:
    confidence = max(0.0, min(1.0, draft.confidence))
    klass: Klass = draft.klass
    rule: PolicyRule | None = None
    rubric: Rubric | None = None
    note = ""
    if klass in ("machine", "human") and draft.rule is not None:
        res = check_rule(draft.rule, tools)
        if not res.ok and res.repairable and not res.fatal and res.rule is not None:
            fixed = await meter.ask(
                repair_messages(tools, clause, res.problems), ProposalDraft, attempts=1
            )
            if isinstance(fixed, ProposalDraft) and fixed.rule is not None:
                res = check_rule(fixed.rule, tools)
        if res.ok and res.rule is not None:
            rule = _unique_rule_id(_apply_defaults(res.rule, clause, klass), clause, used_ids)
        else:
            note = f" Downgraded: {'; '.join(res.problems)}."
            klass = "model"
    elif klass == "machine":
        note = " Downgraded: no rule was proposed."
        klass = "model"
    if klass == "model":
        rubric = await _rubric_for(clause, draft.rubric, policy_id, meter)
        if rubric is None:
            klass = "human"
            note += " No rubric could be drafted."
    return Proposal(
        clause_id=clause.id,
        clause_text=clause.text,
        klass=klass,
        rule=rule,
        rubric=rubric,
        confidence=confidence,
        rationale=draft.rationale + note,
    )


def _fallback(clause: Clause, why: str) -> Proposal:
    return Proposal(
        clause_id=clause.id,
        clause_text=clause.text,
        klass="human",
        confidence=0.0,
        rationale=why,
    )


async def compile_policy(
    text: str,
    *,
    tools: Sequence[ToolSpec],
    gateway: Gateway,
    policy_id: str,
    seed: int = 0,
) -> CompiledPolicy:
    clauses = split_clauses(text)
    meter = _Meter(gateway, seed)
    proposals: list[Proposal] = []
    used_ids: set[str] = set()
    for i in range(0, len(clauses), BATCH_SIZE):
        batch = clauses[i : i + BATCH_SIZE]
        got = await meter.ask(batch_messages(tools, batch), ProposalBatch, attempts=2)
        drafts = {d.clause_id: d for d in got.items} if isinstance(got, ProposalBatch) else {}
        for clause in batch:
            draft = drafts.get(clause.id)
            if draft is None:
                proposals.append(_fallback(clause, "The model returned no usable proposal."))
            else:
                proposals.append(await _resolve(draft, clause, tools, policy_id, meter, used_ids))
    return CompiledPolicy(
        policy_id=policy_id, clauses=clauses, proposals=proposals, cost=meter.cost
    )
