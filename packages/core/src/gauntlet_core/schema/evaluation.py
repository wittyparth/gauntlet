"""Rubrics and verdicts (contracts section 5)."""

from __future__ import annotations

from typing import Literal

from .common import Cost, Evidence, Model, Severity

VerdictResult = Literal["pass", "fail", "na", "error"]
Stage = Literal["rule", "small", "strong", "human"]


class RubricExample(Model):
    transcript: str
    result: Literal["pass", "fail", "na"]
    why: str


class Rubric(Model):
    id: str
    version: int = 1
    title: str
    question: str
    pass_definition: str
    fail_definition: str
    na_definition: str | None = None
    severity: Severity = "medium"
    hard_fail: bool = False
    scope: Literal["conversation", "step"] = "conversation"
    examples: list[RubricExample] = []
    threshold: float = 0.8  # cascade acceptance confidence, set by calibration
    gating_allowed: bool = False


class Verdict(Model):
    evaluator: str
    rubric_version: int | None = None
    criterion: str
    result: VerdictResult
    severity: Severity = "medium"
    hard_fail: bool = False
    confidence: float = 1.0
    evidence: list[Evidence] = []
    reasoning: str = ""
    stage: Stage = "rule"
    model: str | None = None
    cost: Cost | None = None
    # the small judge's result when the strong judge decided (review queue disagreements, P3-5)
    small_result: VerdictResult | None = None
