"""Simulator guard (03-hard-cores 5.5): cheap per-turn rules plus one small-judge rubric.

A drift hit (`SimIssue.kind == "drift"`: empty, assistant role claim, language switch) means
the simulated user broke character; the caller ends the episode as `simulator_error`. A
`note` hit (`hidden_fact_early`) does not: real users volunteer what they know, so the caller
records a `sim_note` event and carries on. The rubric verdict feeds the flaky-scenario
report, not the outcome.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from gauntlet_core.engine import EpisodeCtx
from gauntlet_core.llm.gateway import Gateway
from gauntlet_core.schema import Persona, Rubric, Scenario, Trajectory, Verdict

from .cascade import evaluate_rubric

SIM_FIDELITY_RUBRIC = Rubric(
    id="simulator_fidelity",
    version=1,
    title="Simulated user fidelity",
    question=(
        "Did the simulated USER stay in character (persona, language, tone) and keep pursuing "
        "the stated goal, without acting like the assistant or leaking facts early?"
    ),
    pass_definition=(
        "Every USER message is consistent with the persona and goal in the extra context."
    ),
    fail_definition=(
        "A USER message breaks character, switches language, speaks as the assistant, ignores "
        "the goal, or volunteers a hidden fact before the agent asked for it."
    ),
    severity="low",
    hard_fail=False,
)

_ASSISTANT_CLAIMS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bas an ai\b",
        r"\bi(?:'m| am) (?:an? |your |the )?(?:ai|virtual|language model|assistant|chatbot)\b",
        r"\bhow (?:can|may) i (?:help|assist) you\b",
        r"\bis there anything else i can help\b",
    )
]
_SCRIPTS = {
    "latin": None,
    "cyrillic": "CYRILLIC",
    "cjk": "CJK",
    "hiragana": "HIRAGANA",
    "katakana": "KATAKANA",
    "hangul": "HANGUL",
    "arabic": "ARABIC",
    "hebrew": "HEBREW",
    "devanagari": "DEVANAGARI",
    "thai": "THAI",
    "greek": "GREEK",
}
_LANG_SCRIPT = {
    "ru": "cyrillic", "uk": "cyrillic", "zh": "cjk", "ja": "japanese", "ko": "hangul",
    "ar": "arabic", "he": "hebrew", "hi": "devanagari", "th": "thai", "el": "greek",
}  # fmt: skip
_STOP = {"the", "and", "that", "with", "this", "from", "have", "will", "your", "about", "their"}


@dataclass(frozen=True)
class SimIssue:
    code: str  # empty | claims_assistant | language_switch | hidden_fact_early
    detail: str

    @property
    def kind(self) -> str:
        """`note` (record and continue) or `drift` (end the episode)."""
        return "note" if self.code in NOTE_CODES else "drift"


NOTE_CODES = frozenset({"hidden_fact_early"})
_EXPECTED = {"japanese": {"cjk", "hiragana", "katakana"}}


def _script_of(ch: str) -> str:
    if not ch.isalpha():
        return ""
    name = unicodedata.name(ch, "")
    for key, token in _SCRIPTS.items():
        if token and token in name:
            return key
    return "latin" if "LATIN" in name else "other"


def _tokens(fact: str) -> tuple[list[str], list[str]]:
    """(reveal tokens, ask cues): identifiers and numbers reveal a fact; the other content
    words are what an agent's question would mention."""
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9_@.#-]*", fact)
    reveal = [w.strip(".-") for w in words if any(c.isdigit() for c in w) or "@" in w]
    cues = [w.lower() for w in words if len(w) >= 4 and w not in reveal and w.lower() not in _STOP]
    return [r for r in reveal if len(r) >= 3], cues


class SimulatorGuard:
    def __init__(self, *, hidden_facts: Sequence[str] = (), persona_language: str | None = None):
        self.facts = [(f, *_tokens(f)) for f in hidden_facts]
        self.lang = (persona_language or "en").lower()[:2]
        script = _LANG_SCRIPT.get(self.lang, "latin")
        self.expected = _EXPECTED.get(script, {script})

    def check(self, text: str, agent_messages: Sequence[str]) -> SimIssue | None:
        """`agent_messages` are the agent's messages so far (what could have asked)."""
        if not text.strip():
            return SimIssue("empty", "simulated user message is empty")
        if any(rx.search(text) for rx in _ASSISTANT_CLAIMS):
            return SimIssue("claims_assistant", "message speaks as the assistant")
        letters = [c for c in text if c.isalpha()]
        if letters:
            off = sum(1 for c in letters if _script_of(c) not in self.expected)
            if off / len(letters) > 0.5:
                return SimIssue("language_switch", f"expected {self.lang}, got another script")
        lowered = text.lower()
        asked = [m.lower() for m in agent_messages if "?" in m]
        for fact, reveal, cues in self.facts:
            if not any(r.lower() in lowered for r in reveal):
                continue
            if any(c in m for m in asked for c in cues) or any(
                r.lower() in m for m in asked for r in reveal
            ):
                continue
            return SimIssue("hidden_fact_early", f"revealed before being asked: {fact[:60]}")
        return None


def sim_context(scenario: Scenario, persona: Persona) -> str:
    rules = "; ".join(persona.behavior_rules) or "none"
    facts = "; ".join(scenario.hidden_facts) or "none"
    return (
        f"Simulated user persona: {persona.name}. {persona.description}\n"
        f"Behavior rules: {rules}\nGoal: {scenario.goal}\n"
        f"Facts the user should only reveal when asked: {facts}"
    )


async def evaluate_sim_fidelity(
    traj: Trajectory, gateway: Gateway, context_text: str, *, ctx: EpisodeCtx | None = None
) -> Verdict:
    """Small judge only (no escalation); an invalid small verdict is reported as `error`."""
    return await evaluate_rubric(
        SIM_FIDELITY_RUBRIC,
        traj,
        gateway,
        ctx=ctx,
        context_text=context_text,
        escalate=False,
        evaluator="judge:simulator_fidelity",
    )
