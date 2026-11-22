"""Deterministic failure signals over a production conversation (P5-2). Each returns a value
in [0, 1] and the reasons behind it; none needs a model."""

from __future__ import annotations

import difflib
import itertools
import re
from collections.abc import Sequence

from gauntlet_core.schema import Event

__all__ = [
    "abandonment",
    "dissatisfaction",
    "human_request",
    "redaction_leak",
    "rephrasing",
]

_DISSATISFIED = re.compile(
    r"(?i)\b(not helpful|useless|that'?s (not|wrong)|this is wrong|not what i (asked|wanted)|"
    r"terrible|awful|frustrat\w*|doesn'?t work|you'?re not listening|waste of time|"
    r"still (not|no)|ridiculous|unacceptable)\b"
)
_HUMAN = re.compile(
    r"(?i)\b(talk|speak|connect|transfer)\b[^.?!]{0,30}\b(human|person|agent|representative|"
    r"manager|supervisor|someone)\b|\breal (person|human)\b|\bhuman agent\b"
)
_APOLOGY = re.compile(r"(?i)\b(sorry|apologi[sz]e|unfortunately)\b")
# Typed redaction tokens that mean the agent's own output carried something sensitive.
_SENSITIVE_TOKEN = re.compile(r"\[(CARD|SECRET|SSN|IBAN)_[0-9a-f]{6}\]")


def _user_texts(events: Sequence[Event]) -> list[str]:
    return [str(e.payload.get("text", "")) for e in events if e.kind == "user_message"]


def _norm(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def rephrasing(events: Sequence[Event]) -> tuple[float, list[str]]:
    """The user says nearly the same thing again after the agent answered."""
    texts, hits = _user_texts(events), 0
    for a, b in itertools.pairwise(texts):
        ta, tb = _norm(a), _norm(b)
        if len(ta) >= 3 and len(tb) >= 3 and difflib.SequenceMatcher(None, ta, tb).ratio() >= 0.6:
            hits += 1
    return (min(1.0, 0.5 * hits), [f"user repeated a request {hits}x"] if hits else [])


def dissatisfaction(events: Sequence[Event]) -> tuple[float, list[str]]:
    hits = sum(1 for t in _user_texts(events) if _DISSATISFIED.search(t))
    return (
        min(1.0, 0.5 * hits),
        [f"explicit dissatisfaction in {hits} message(s)"] if hits else [],
    )


def human_request(events: Sequence[Event]) -> tuple[float, list[str]]:
    hits = sum(1 for t in _user_texts(events) if _HUMAN.search(t))
    return (min(1.0, 0.6 * hits), ["user asked for a human"] if hits else [])


def abandonment(events: Sequence[Event]) -> tuple[float, list[str]]:
    """Ends on a user message nobody answered, or on an apology within the first two turns."""
    msgs = [e for e in events if e.kind in ("user_message", "agent_message")]
    if not msgs:
        return 0.0, []
    last = msgs[-1]
    if last.kind == "user_message":
        return 0.5, ["the last user message was never answered"]
    turns = len(_user_texts(events))
    if turns <= 2 and _APOLOGY.search(str(last.payload.get("text", ""))):
        return 0.4, ["the conversation ended on an apology"]
    return 0.0, []


def redaction_leak(events: Sequence[Event]) -> tuple[float, list[str]]:
    """Ingest redacted a card, secret, SSN or IBAN out of the *agent's* output: the agent said
    something it should not have (the value itself is gone, only its type is known)."""
    kinds = sorted(
        {
            m.group(1).lower()
            for e in events
            if e.kind == "agent_message"
            for m in _SENSITIVE_TOKEN.finditer(str(e.payload.get("text", "")))
        }
    )
    if not kinds:
        return 0.0, []
    return 1.0, [f"agent output contained a {', '.join(kinds)}"]
