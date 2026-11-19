"""Loop detector over the event list: repeated identical tool calls or agent messages."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

from gauntlet_core.schema import Event

from .types import Hit, clip


def _norm_msg(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _call_sig(e: Event) -> str:
    args = json.dumps(e.payload.get("args", {}), sort_keys=True, default=str)
    return f"{e.payload.get('tool', '')}({args})"


def _runs(items: list[tuple[int, str]], min_repeats: int) -> list[tuple[str, list[int]]]:
    out: list[tuple[str, list[int]]] = []
    i = 0
    while i < len(items):
        j = i
        while j + 1 < len(items) and items[j + 1][1] == items[i][1]:
            j += 1
        if j - i + 1 >= min_repeats:
            out.append((items[i][1], [s for s, _ in items[i : j + 1]]))
        i = j + 1
    return out


def detect_loop(events: Sequence[Event], *, min_repeats: int = 3, max_total: int = 5) -> list[Hit]:
    """Consecutiveness is judged within one event kind, so unrelated events in between
    (results, user turns, notes) neither break nor create a loop."""
    calls = [(e.seq, _call_sig(e)) for e in events if e.kind == "tool_call"]
    msgs = [
        (e.seq, n)
        for e in events
        if e.kind == "agent_message" and (n := _norm_msg(str(e.payload.get("text", ""))))
    ]
    seqs: dict[int, Hit] = {}

    def add(label: str, sig: str, ss: list[int]) -> None:
        for s in ss:
            seqs.setdefault(s, Hit(label, clip(sig), s))

    for sig, ss in _runs(calls, min_repeats):
        add("repeated_tool_call", sig, ss)
    totals: dict[str, list[int]] = {}
    for s, sig in calls:
        totals.setdefault(sig, []).append(s)
    for sig, ss in totals.items():
        if len(ss) >= max_total:
            add("repeated_tool_call", sig, ss)
    for sig, ss in _runs(msgs, min_repeats):
        add("repeated_message", sig, ss)
    return [seqs[s] for s in sorted(seqs)]
