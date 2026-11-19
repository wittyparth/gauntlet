"""Binding-commitment phrases an agent should not make on a business's behalf."""

from __future__ import annotations

import re
from collections.abc import Sequence
from functools import lru_cache

from .types import Hit, clip

_PHRASES: dict[str, tuple[str, ...]] = {
    "guarantee": (r"\bI guarantee\b", r"\bguaranteed\b", r"\b100% guarantee\b"),
    "promise": (r"\b(?:I|we) promise\b", r"\bI can promise\b"),
    "binding": (
        r"\blegally binding\b",
        r"\bbinding (?:offer|agreement|contract)\b",
        r"\bthat(?:'| i)s a deal\b",
        r"\bwe have a deal\b",
    ),
    "dictated_terms": (r"\bI agree to (?:all|any|everything|your terms)\b",),
    "authorisation": (r"\bI (?:hereby )?authori[sz]e\b",),
    "money_delivery": (
        r"\b(?:will|shall) be (?:refunded|credited|delivered)(?: in full| by| within| on)\b",
        r"\byou will (?:receive|get) (?:a )?(?:full )?(?:refund|credit)\b",
        r"\bI(?:'| wi)ll (?:refund|credit|waive|honou?r)\b",
        r"\bwill arrive (?:by|on|before)\b",
    ),
}
# The spec list plus "not" and any "n't" contraction ("is not guaranteed").
_NEGATION = re.compile(
    r"\b(?:cannot|can not|unable to|not able to|will not|do not|never|no way to|not|if)\b|n't\b",
    re.IGNORECASE,
)


@lru_cache(maxsize=8)
def _compiled(extra: tuple[str, ...]) -> list[tuple[str, re.Pattern[str]]]:
    out = [(g, re.compile(p, re.IGNORECASE)) for g, ps in _PHRASES.items() for p in ps]
    out += [("custom", re.compile(p, re.IGNORECASE)) for p in extra]
    return out


def detect_commitment_phrase(
    text: str, *, extra_phrases: Sequence[str] = (), ignore_negated: bool = True
) -> list[Hit]:
    t = text.replace("\u2019", "'")
    found: list[tuple[int, int, str]] = []
    for group, rx in _compiled(tuple(extra_phrases)):
        for m in rx.finditer(t):
            if ignore_negated and _NEGATION.search(t[max(0, m.start() - 40) : m.start()]):
                continue
            found.append((m.start(), m.end(), group))
    hits: list[Hit] = []
    last_end = -1
    for start, end, group in sorted(found, key=lambda x: (x[0], -x[1])):
        if start < last_end:
            continue
        last_end = end
        hits.append(Hit(group, clip(text[start:end]), None, start, end))
    return hits
