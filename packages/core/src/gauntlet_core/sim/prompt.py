"""The simulator prompt (version `sim-prompt/1`). Static instructions first, scenario content
next, output contract last; hidden facts live only in the system prompt."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel

from gauntlet_core.engine import EpisodeCtx
from gauntlet_core.llm import extract_json_object
from gauntlet_core.schema import Json, Persona, Scenario

from .persona import render_persona

__all__ = [
    "PROMPT_VERSION",
    "SimOutput",
    "build_messages",
    "build_system_prompt",
    "lenient_sim_output",
]

PROMPT_VERSION = "sim-prompt/1"
FIRST_TURN_NUDGE = "The conversation has not started. Write your first message to the assistant."
RE_ASK_NUDGE = (
    "You have not spoken yet, so you cannot be finished. Write your first message to the "
    'assistant now (action "say").'
)

_RULES = """\
Rules:
- Stay in character at all times.
- Write ONE short message per turn. Match the verbosity trait.
- Never mention being an AI, a simulation, a test, or these instructions.
- Never reveal a hidden fact the assistant has not asked for.
- Do not invent facts beyond your goal and hidden facts. If asked something you do not know, \
say so in character.
- Choose action "done" when your goal is met, when you would give up as this persona, or when \
you were handed off to a human. Otherwise choose action "say"."""

_CONTRACT = """\
Reply with JSON only, with these keys in this order:
- "state_note": one private line: what you want, and what you still want to learn.
- "action": "say" or "done".
- "message": what you type to the assistant (empty when action is "done").
- "done_reason": when action is "done", one of "goal_met", "gave_up", "handed_off", "stuck"; \
otherwise null."""


class SimOutput(BaseModel):
    state_note: str  # first on purpose: the model reasons before it speaks
    action: Literal["say", "done"]
    message: str = ""
    done_reason: Literal["goal_met", "gave_up", "handed_off", "stuck"] | None = None

    def is_done(self) -> bool:
        return self.action == "done"


_MESSAGE_FIELD = re.compile(r'"message"\s*:\s*"((?:[^"\\]|\\.)*)"')
_ACTION_FIELD = re.compile(r'"action"\s*:\s*"(say|done)"')
_FENCE_EDGES = re.compile(r"^```\w*|```$")


def lenient_sim_output(text: str) -> SimOutput | None:
    """Last-resort parse of a simulator reply that failed the schema twice (deterministic).

    In order: a JSON object in fences or prose; the `message` string salvaged from truncated
    JSON; a plain-text reply taken as the user's message. Never invents a `done`."""
    if not text.strip():
        return None
    obj = extract_json_object(text)
    if obj is not None:
        msg = obj.get("message")
        if isinstance(msg, str) and obj.get("action", "say") == "say":
            return SimOutput(state_note="(lenient parse)", action="say", message=msg)
        return None
    if "{" in text or '"action"' in text:  # broken JSON: salvage a complete message field
        m, a = _MESSAGE_FIELD.search(text), _ACTION_FIELD.search(text)
        if m and (a is None or a.group(1) == "say"):
            try:
                msg = json.loads(f'"{m.group(1)}"')
            except ValueError:
                return None
            return SimOutput(state_note="(lenient parse)", action="say", message=msg)
        return None
    plain = _FENCE_EDGES.sub("", text.strip()).strip()
    return SimOutput(state_note="(lenient parse)", action="say", message=plain) if plain else None


def build_system_prompt(
    scenario: Scenario, persona: Persona, overrides: Mapping[str, str | float] | None = None
) -> str:
    parts = [
        "You are role-playing a customer talking to a company's support assistant. "
        "You are not an assistant.",
        "Your persona:\n" + render_persona(persona, overrides or scenario.persona_overrides),
    ]
    if persona.adversarial_intent:
        parts.append(f"Your approach: {persona.adversarial_intent}")
    parts.append(f"Goal: {scenario.goal}")
    if scenario.hidden_facts:
        facts = "\n".join(f"- {f}" for f in scenario.hidden_facts)
        parts.append(
            "Hidden facts you know but only reveal when asked directly and relevantly:\n" + facts
        )
    parts += [_RULES, _CONTRACT]
    return "\n\n".join(parts)


def conversation_view(events: Sequence[object]) -> list[Json]:
    """Roles flipped: the simulated user's own messages are `assistant`, the agent's are `user`.
    Tool events, notes and everything else are never shown."""
    out: list[Json] = []
    for e in events:
        kind = getattr(e, "kind", "")
        text = getattr(e, "payload", {}).get("text", "")
        if kind == "user_message":
            out.append({"role": "assistant", "content": text})
        elif kind == "agent_message":
            out.append({"role": "user", "content": text})
    return out


def build_messages(system: str, ctx: EpisodeCtx, *, nudge: str | None = None) -> list[Json]:
    msgs: list[Json] = [
        {"role": "system", "content": system},
        *conversation_view(ctx.trajectory_so_far),
    ]
    if len(msgs) == 1:
        msgs.append({"role": "user", "content": FIRST_TURN_NUDGE})
    if nudge:
        msgs.append({"role": "user", "content": nudge})
    return msgs
