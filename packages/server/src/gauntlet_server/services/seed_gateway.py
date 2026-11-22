"""Dev-seed fixtures for the gateway screens: a published policy with proposals, a finished policy
test, a few decisions and one pending approval. Everything is plain rows; nothing calls a model."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from gauntlet_core.gateway import DecisionRecord
from gauntlet_core.policy import PolicyTestReport
from gauntlet_core.policy.compile import CompiledPolicy
from gauntlet_core.schema import Policy
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.policy_models import (
    GatewayApprovalRow,
    GatewayDecisionRow,
    PolicyProposalRow,
    PolicyTestRow,
    PolicyVersion,
)
from .policies import dump_doc

__all__ = ["POLICY", "seed_gateway"]

POLICY = "pol_demo"
SOURCE = (
    "1. Refunds above $100 need a human to approve them.\n"
    "2. Never email a customer's card number.\n"
    "3. Be polite in every reply.\n"
)


def _rule(rid: str, description: str, tool: str, action: str, severity: str) -> dict[str, Any]:
    return {
        "id": rid,
        "description": description,
        "severity": severity,
        "when": {"type": "tool_called", "tool": tool},
        "action": action,
        "message": f"{tool} is held by {rid}",
    }


def _proposals() -> CompiledPolicy:
    refund = _rule(
        "refund-cap", "Refunds need approval", "issue_refund", "require_approval", "high"
    )
    email = _rule("no-card-email", "Do not email card numbers", "send_email", "block", "critical")
    return CompiledPolicy.model_validate(
        {
            "policy_id": POLICY,
            "clauses": [
                {"id": "c1", "text": SOURCE.splitlines()[0][3:], "source_span": [0, 55]},
                {"id": "c2", "text": SOURCE.splitlines()[1][3:], "source_span": [56, 93]},
                {"id": "c3", "text": SOURCE.splitlines()[2][3:], "source_span": [94, 119]},
            ],
            "proposals": [
                {"clause_id": "c1",
                 "clause_text": "Refunds above $100 need a human to approve them.",
                 "klass": "machine", "rule": refund, "confidence": 0.9,
                 "rationale": "A refund tool call is checkable on its own.", "status": "accepted"},
                {"clause_id": "c2", "clause_text": "Never email a customer's card number.",
                 "klass": "machine", "rule": email, "confidence": 0.8,
                 "rationale": "Email is an egress tool.", "status": "accepted"},
                {"clause_id": "c3", "clause_text": "Be polite in every reply.",
                 "klass": "human", "rule": None, "confidence": 0.5,
                 "rationale": "Tone needs a judge, not a rule.", "status": "proposed"},
            ],
        }
    )  # fmt: skip


def _report() -> dict[str, Any]:
    return PolicyTestReport.model_validate(
        {
            "attacks": 4, "benign": 10, "skipped": 1, "blocked": 3, "broken": 1,
            "block_rate": 0.75, "fp_rate": 0.1,
            "per_rule": [
                {"rule_id": "no-card-email", "blocked": 2, "false_positives": 0},
                {"rule_id": "refund-cap", "blocked": 1, "false_positives": 1},
            ],
            "tradeoff": [
                {"rules": ["no-card-email"], "added": "no-card-email", "blocked": 2,
                 "false_positives": 0, "block_rate": 0.5, "fp_rate": 0.0},
                {"rules": ["no-card-email", "refund-cap"], "added": "refund-cap", "blocked": 3,
                 "false_positives": 1, "block_rate": 0.75, "fp_rate": 0.1},
            ],
            "outcomes": [
                {"episode_id": "ep_demo_0", "kind": "attack", "first_block_seq": 4,
                 "rule_id": "no-card-email", "objective_seq": 6, "effective": True},
                {"episode_id": "ep_demo_1", "kind": "benign", "first_block_seq": 3,
                 "rule_id": "refund-cap", "objective_seq": None, "effective": True},
            ],
        }
    ).model_dump(mode="json")  # fmt: skip


def _decision(i: int, now: datetime, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": f"gdc_demo_{i:02d}",
        "ts": now - timedelta(minutes=i),
        "session_id": "ses_demo",
        "agent_id": "agt_demo",
        "policy_id": POLICY,
        "policy_version": 1,
        "mode": "shadow",
        "kind": "tool_call",
        "tool": "lookup_order",
        "args": {"order_id": "ord_1001"},
        "action": "allow",
        "enforced": False,
        "overhead_us": 120 + i * 7,
    }
    return DecisionRecord.model_validate({**base, **kw}).model_dump(mode="json")


async def seed_gateway(s: AsyncSession, ws: str, agent_id: str, agent_version_id: str) -> None:
    if await s.get(PolicyVersion, (POLICY, 1)) is not None:
        return
    now = datetime.now(UTC).replace(microsecond=0)
    compiled = _proposals()
    rules = [p.rule for p in compiled.proposals if p.status == "accepted" and p.rule]
    s.add(
        PolicyVersion(
            id=POLICY, version=1, workspace_id=ws, name="Support policy", agent_id=agent_id,
            doc=dump_doc(Policy(id=POLICY, version=1, rules=rules, mode="shadow", fail="open")),
            status="published", source_text=SOURCE,
        )
    )  # fmt: skip
    s.add(
        PolicyProposalRow(
            id="ppr_demo", workspace_id=ws, policy_id=POLICY, version=1, doc=dump_doc(compiled)
        )
    )
    report = _report()
    s.add(
        PolicyTestRow(
            id="ptt_demo", workspace_id=ws, policy_id=POLICY, policy_version=1,
            agent_version_id=agent_version_id, status="done", result=report,
            attack_count=4, benign_count=10, finished_at=now,
        )
    )  # fmt: skip
    specs: list[dict[str, Any]] = [
        {"action": "block", "mode": "enforce", "enforced": True, "tool": "send_email",
         "rule_id": "no-card-email", "severity": "critical",
         "message": "send_email is held by no-card-email",
         "args": {"to": "x@example.test", "body": "card 4111"},
         "episode_id": "ep_demo_0", "evidence": [{"seq": 4, "quote": "card 4111"}]},
        {"action": "require_approval", "tool": "issue_refund", "rule_id": "refund-cap",
         "severity": "high", "would_have": "require_approval", "args": {"amount_cents": 48000},
         "approval": {"id": "gap_demo", "outcome": "pending"}},
        {"action": "allow", "tool": "lookup_order"},
        {"action": "log", "tool": "issue_refund", "rule_id": "refund-cap", "severity": "high",
         "args": {"amount_cents": 500}},
        {"action": "redact", "kind": "output", "tool": None, "args": None,
         "rule_id": "no-card-email",
         "severity": "critical", "message": "card number removed"},
        {"action": "allow", "tool": "lookup_order"},
    ]  # fmt: skip
    for i, extra in enumerate(specs, start=1):
        doc = _decision(i, now, **extra)
        s.add(
            GatewayDecisionRow(
                id=doc["id"], workspace_id=ws, ts=now - timedelta(minutes=i),
                session_id=doc["session_id"], agent_id=doc["agent_id"], policy_id=POLICY,
                policy_version=1, mode=doc["mode"], kind=doc["kind"], tool=doc["tool"],
                action=doc["action"], enforced=doc["enforced"], rule_id=doc["rule_id"],
                severity=doc["severity"], overhead_us=doc["overhead_us"], doc=doc,
            )
        )  # fmt: skip
        if extra.get("approval"):
            s.add(
                GatewayApprovalRow(
                    id="gap_demo", workspace_id=ws, decision_doc=doc, status="pending",
                    requested_at=now - timedelta(minutes=i), expires_at=now + timedelta(days=1),
                )
            )  # fmt: skip
    await s.flush()
