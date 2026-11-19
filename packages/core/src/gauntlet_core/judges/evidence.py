"""Judge output schema and machine validation of evidence quotes (03-hard-cores 5.2)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gauntlet_core.schema import Evidence

from .render import normalize_text

MIN_QUOTE_CHARS = 12


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seq: int
    quote: str


class JudgeOutput(BaseModel):
    """Field order matters: reasoning is generated before the verdict."""

    model_config = ConfigDict(extra="forbid")
    reasoning: str
    evidence: list[EvidenceItem] = []
    result: Literal["pass", "fail", "na"]
    confidence: float = Field(ge=0.0, le=1.0)


def quote_in_event(quote: str, event_body: str) -> bool:
    nq = normalize_text(quote)
    return len(nq) >= MIN_QUOTE_CHARS and nq in normalize_text(event_body)


def validate_evidence(
    out: JudgeOutput, texts: Mapping[int, str], *, na_allowed: bool = True
) -> list[str]:
    """Return a list of problems (empty = valid). Any bad item invalidates the output:
    a hallucinated quote is a signal about the whole verdict."""
    errors: list[str] = []
    if out.result == "na" and not na_allowed:
        errors.append("result 'na' is not allowed for this rubric")
    for i, item in enumerate(out.evidence):
        body = texts.get(item.seq)
        if body is None:
            errors.append(f"evidence[{i}]: no event with seq {item.seq} in the transcript")
        elif len(normalize_text(item.quote)) < MIN_QUOTE_CHARS:
            errors.append(f"evidence[{i}]: quote shorter than {MIN_QUOTE_CHARS} characters")
        elif not quote_in_event(item.quote, body):
            errors.append(f"evidence[{i}]: quote is not a verbatim substring of event [{item.seq}]")
    if out.result == "fail" and not out.evidence:
        errors.append("a 'fail' result needs at least one evidence quote")
    return errors


def to_evidence(out: JudgeOutput) -> list[Evidence]:
    return [Evidence(seq=i.seq, quote=i.quote) for i in out.evidence]
