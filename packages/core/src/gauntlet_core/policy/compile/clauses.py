"""Split a policy text into clauses (P4-1): numbered or bulleted items and blank-line
paragraphs. Sentences stay together unless the clause exceeds 400 characters."""

from __future__ import annotations

import re

from gauntlet_core.schema import Model

__all__ = ["MAX_CLAUSE", "Clause", "split_clauses"]

MAX_CLAUSE = 400
_ITEM = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+")
_SENTENCE_END = re.compile(r"(?<=[.!?;])\s+")
_WS = re.compile(r"\s*\n\s*")


class Clause(Model):
    id: str
    text: str
    source_span: tuple[int, int]  # [start, end) offsets into the source text


def _pieces(raw: str, start: int) -> list[tuple[str, int, int]]:
    """Split an over-long clause at `;` or sentence ends, packing up to MAX_CLAUSE."""
    if len(raw) <= MAX_CLAUSE:
        return [(raw, start, start + len(raw))]
    out: list[tuple[str, int, int]] = []
    cur = 0
    last_end = 0
    for m in _SENTENCE_END.finditer(raw):
        if m.start() - cur > MAX_CLAUSE and last_end > cur:
            out.append((raw[cur:last_end], start + cur, start + last_end))
            cur = last_end
            while cur < len(raw) and raw[cur].isspace():
                cur += 1
        last_end = m.start()
    out.append((raw[cur:], start + cur, start + len(raw)))
    return [p for p in out if p[0].strip()]


def split_clauses(text: str) -> list[Clause]:
    blocks: list[tuple[int, int, bool]] = []  # start, end, is_list_item
    cur: tuple[int, int, bool] | None = None
    offset = 0
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        lstart, lend = offset, offset + len(body)
        offset += len(line)
        stripped = body.strip()
        if not stripped or stripped.startswith("#"):
            if cur:
                blocks.append(cur)
                cur = None
            continue
        item = _ITEM.match(body)
        if item:
            if cur:
                blocks.append(cur)
            cur = (lstart + item.end(), lend, True)
        elif cur:
            cur = (cur[0], lend, cur[2])  # continuation line
        else:
            cur = (lstart + (len(body) - len(body.lstrip())), lend, False)
    if cur:
        blocks.append(cur)
    # Free paragraphs before the first list item are a preamble, not rules.
    first_item = next((i for i, b in enumerate(blocks) if b[2]), 0)
    clauses: list[Clause] = []
    for start, end, _ in blocks[first_item:]:
        for piece, ps, pe in _pieces(text[start:end], start):
            body = _WS.sub(" ", piece).strip()
            if body:
                clauses.append(
                    Clause(id=f"c{len(clauses) + 1:02d}", text=body, source_span=(ps, pe))
                )
    return clauses
