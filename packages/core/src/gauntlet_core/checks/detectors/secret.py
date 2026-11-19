"""Secret detector: provider key formats plus entropy-gated generic assignments."""

from __future__ import annotations

import math
import re
from collections import Counter

from .types import Hit, clip

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("stripe_key", re.compile(r"\b[sr]k_live_[0-9a-zA-Z]{24,}\b")),
    ("api_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("api_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("google_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    ),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
]
_ASSIGN = re.compile(
    r"""\b(api[_-]?key|secret|token|passwd|password)\b\s*[:=]\s*['"]?([A-Za-z0-9_\-/+=]{16,})""",
    re.IGNORECASE,
)


def shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in Counter(s).values())


def detect_secret(text: str, *, min_entropy: float = 3.5) -> list[Hit]:
    hits: list[Hit] = []
    taken: list[tuple[int, int]] = []

    def free(s: int, e: int) -> bool:
        return not any(s < te and ts < e for ts, te in taken)

    for label, rx in _PATTERNS:
        for m in rx.finditer(text):
            if free(m.start(), m.end()):
                taken.append((m.start(), m.end()))
                hits.append(Hit(label, clip(m.group()), None, m.start(), m.end()))
    for m in _ASSIGN.finditer(text):
        if shannon_entropy(m.group(2)) >= min_entropy and free(m.start(), m.end()):
            taken.append((m.start(), m.end()))
            hits.append(Hit("generic_secret", clip(m.group()), None, m.start(), m.end()))
    return sorted(hits, key=lambda h: h.start or 0)
