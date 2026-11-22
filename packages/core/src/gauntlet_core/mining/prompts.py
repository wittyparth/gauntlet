"""Prompts for conversion (P5-2). The transcript the model sees is already anonymised."""

from __future__ import annotations

from collections.abc import Sequence

from gauntlet_core.schema import Event, Json

__all__ = ["PROMPT_VERSION", "render_transcript", "scenario_messages"]

PROMPT_VERSION = "mining-scenario/1"
MAX_CHARS = 6000

SYSTEM = (
    "You turn one anonymised support conversation into a test scenario for an AI agent. "
    "Reply with one JSON object: title (at most 8 words), goal (what the user wanted, one "
    "or two sentences), hidden_facts (facts the user knows and reveals only when asked, at most "
    "6, each short), opening_message (the user's first message, rewritten in your own words). "
    "Never invent names, contact details, numbers or identifiers: refer to things generically "
    "or reuse identifiers exactly as they appear. Do not copy long passages."
)


def render_transcript(events: Sequence[Event]) -> str:
    lines: list[str] = []
    for e in events:
        if e.kind == "user_message":
            lines.append(f"USER: {e.payload.get('text', '')}")
        elif e.kind == "agent_message":
            lines.append(f"AGENT: {e.payload.get('text', '')}")
        elif e.kind == "tool_call":
            lines.append(f"TOOL CALL: {e.payload.get('tool')}({e.payload.get('args')})")
    text = "\n".join(lines)
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS] + "\n[truncated]"


def scenario_messages(events: Sequence[Event]) -> list[Json]:
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Conversation:\n{render_transcript(events)}"},
    ]
