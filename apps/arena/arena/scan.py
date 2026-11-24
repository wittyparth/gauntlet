"""Output scan (P1-4 detectors) before a reply leaves the arena: anything that looks like a real
secret or personal datum is masked. The arena holds fake data only; this is the second line."""

from __future__ import annotations

import re

from gauntlet_core.checks.detectors.pii import detect_pii
from gauntlet_core.checks.detectors.secret import detect_secret

__all__ = ["scan_output"]

_CANARY_SPAN = re.compile(r"A\W*R\W*E\W*N\W*A\W*[0-9A-Fa-f]")


def scan_output(text: str) -> tuple[str, int]:
    """Returns the masked text and how many spans were masked. Spans that are the arena's own
    fake token are left alone: showing it is the point of the game and the win check owns it."""
    spans: list[tuple[int, int]] = []
    for h in [*detect_pii(text), *detect_secret(text)]:
        if h.start is None or h.end is None:
            continue
        if _CANARY_SPAN.search(text[max(0, h.start - 6) : h.end]):
            continue
        spans.append((h.start, h.end))
    if not spans:
        return text, 0
    out, last = [], 0
    for s, e in sorted(spans):
        if s < last:
            continue
        out.append(text[last:s])
        out.append("[masked]")
        last = e
    out.append(text[last:])
    return "".join(out), len(spans)
