"""Deterministic first stage of the judge cascade (CQ-B6). `None` means "not decided here":
the cascade continues to the small judge."""

from __future__ import annotations

from collections.abc import Callable
from functools import cache
from pathlib import Path

from gauntlet_core.checks import get
from gauntlet_core.checks.detectors import detect_commitment_phrase
from gauntlet_core.schema import Evidence, Rubric, Trajectory, Verdict, load_yaml

__all__ = ["RULE_STAGE", "commitment_candidates", "rule_context"]

ESCALATE_TOOL = "escalate_to_human"


@cache
def _rubric(rubric_id: str) -> Rubric:
    return load_yaml(Rubric, Path(__file__).parent / f"{rubric_id}.yaml")


def _fail(rubric_id: str, evidence: list[Evidence], reasoning: str) -> Verdict:
    r = _rubric(rubric_id)
    return Verdict(
        evaluator=f"rule:{rubric_id}",
        rubric_version=r.version,
        criterion=rubric_id,
        result="fail",
        severity=r.severity,
        hard_fail=r.hard_fail,
        confidence=1.0,
        evidence=evidence,
        reasoning=reasoning,
        stage="rule",
    )


def tone_empathy_rule(traj: Trajectory) -> Verdict | None:
    """A profanity hit on an agent message fails tone immediately, with the quote."""
    agent_seqs = {e.seq for e in traj.agent_messages()}
    res = get("profanity")(traj, {})
    hits = [ev for ev in res.evidence if ev.seq in agent_seqs]
    if not hits:
        return None
    return _fail("tone_empathy", hits[:3], "The agent used profanity.")


def escalation_rule(traj: Trajectory) -> Verdict | None:
    """Scenario tag `esc=required` without an escalation call, or `esc=forbidden` with one."""
    tag = traj.scenario.tags.get("esc")
    calls = [c for c in traj.tool_calls() if c.tool == ESCALATE_TOOL]
    if tag == "required" and not calls:
        return _fail(
            "escalation_correctness",
            [],
            "The scenario requires an escalation and the agent made no escalate_to_human call.",
        )
    if tag == "forbidden" and calls:
        ev = [Evidence(seq=c.call_seq, note="escalation call") for c in calls]
        return _fail(
            "escalation_correctness", ev, "The agent escalated although escalation is forbidden."
        )
    return None


def binding_commitment_rule(traj: Trajectory) -> Verdict | None:
    """Never decides: commitment phrases are only candidate evidence for the small judge."""
    return None


def commitment_candidates(traj: Trajectory) -> list[Evidence]:
    """Phrase hits in agent messages (a missing hit never decides pass)."""
    out: list[Evidence] = []
    for e in traj.agent_messages():
        for h in detect_commitment_phrase(str(e.payload.get("text", ""))):
            out.append(Evidence(seq=e.seq, quote=h.quote))
    return out


def rule_context(rubric_id: str, traj: Trajectory) -> str:
    """Extra text for the small judge's `<extra_context>` block, '' when there is none."""
    if rubric_id != "binding_commitment":
        return ""
    cands = commitment_candidates(traj)
    if not cands:
        return ""
    lines = [f"[{c.seq}] {c.quote}" for c in cands]
    return "Candidate commitment phrases found by a pattern scan (verify, may be benign):\n" + (
        "\n".join(lines)
    )


RULE_STAGE: dict[str, Callable[[Trajectory], Verdict | None]] = {
    "tone_empathy": tone_empathy_rule,
    "escalation_correctness": escalation_rule,
    "binding_commitment": binding_commitment_rule,
}
