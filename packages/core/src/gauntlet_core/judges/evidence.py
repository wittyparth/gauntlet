"""Judge output schema and machine validation of evidence quotes (03-hard-cores 5.2)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gauntlet_core.schema import Evidence

from .render import normalize_quote, normalize_text

MIN_QUOTE_CHARS = 4


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
    nq = normalize_quote(quote)
    return len(nq) >= MIN_QUOTE_CHARS and nq in normalize_text(event_body)


REANCHOR_WINDOW = 2


@dataclass
class EvidenceCheck:
    """Per-item evidence outcome: surviving (possibly re-anchored) items, dropped-item reasons,
    and the problems that make the whole output invalid."""

    kept: list[EvidenceItem] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _check_item(
    item: EvidenceItem, texts: Mapping[int, str], actors: Mapping[int, str] | None
) -> tuple[EvidenceItem | None, str | None]:
    body = texts.get(item.seq)
    if body is None:
        return None, f"no event with seq {item.seq} in the transcript"
    if len(normalize_quote(item.quote)) < MIN_QUOTE_CHARS:
        return None, f"quote shorter than {MIN_QUOTE_CHARS} characters"
    if quote_in_event(item.quote, body):
        return item, None
    if actors is not None and item.seq in actors:
        for seq in sorted(texts, key=lambda s: (abs(s - item.seq), s)):
            if (
                seq != item.seq
                and abs(seq - item.seq) <= REANCHOR_WINDOW
                and actors.get(seq) == actors[item.seq]
                and quote_in_event(item.quote, texts[seq])
            ):
                return EvidenceItem(seq=seq, quote=item.quote), None
    return None, f"quote is not a verbatim substring of event [{item.seq}]"


def check_evidence(
    out: JudgeOutput,
    texts: Mapping[int, str],
    actors: Mapping[int, str] | None = None,
    *,
    na_allowed: bool = True,
) -> EvidenceCheck:
    """Validate each evidence item independently and drop the invalid ones. A `fail` is valid
    only if at least one item survives; `pass` and `na` are valid with none."""
    res = EvidenceCheck()
    if out.result == "na" and not na_allowed:
        res.errors.append("result 'na' is not allowed for this rubric")
    for i, item in enumerate(out.evidence):
        ok, why = _check_item(item, texts, actors)
        if ok is not None:
            res.kept.append(ok)
        else:
            res.dropped.append(f"evidence[{i}]: {why}")
    if out.result == "fail" and not res.kept:
        res.errors.extend(res.dropped)
        res.errors.append("a 'fail' result needs at least one valid evidence quote")
    return res


def validate_evidence(
    out: JudgeOutput,
    texts: Mapping[int, str],
    actors: Mapping[int, str] | None = None,
    *,
    na_allowed: bool = True,
) -> list[str]:
    """Problems that invalidate the output (empty = valid); see `check_evidence`."""
    return check_evidence(out, texts, actors, na_allowed=na_allowed).errors


def sanitize(out: JudgeOutput, check: EvidenceCheck) -> JudgeOutput:
    """The output restricted to surviving evidence, with a reasoning suffix noting drops."""
    if not check.dropped:
        return out
    n = len(check.dropped)
    suffix = f" [{n} evidence quote{'s' if n != 1 else ''} dropped: {'; '.join(check.dropped)}]"
    return out.model_copy(update={"evidence": check.kept, "reasoning": out.reasoning + suffix})


def to_evidence(out: JudgeOutput) -> list[Evidence]:
    return [Evidence(seq=i.seq, quote=i.quote) for i in out.evidence]
