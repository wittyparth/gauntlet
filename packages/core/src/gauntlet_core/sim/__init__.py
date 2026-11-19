"""User simulation: personas, the LLM simulator, a scripted simulator, typo injection."""

from .persona import load_persona_library, merge_persona, render_persona
from .prompt import PROMPT_VERSION, SimOutput, build_system_prompt, lenient_sim_output
from .scripted import ScriptedUserSimulator
from .simulator import GuardHit, LLMUserSimulator, SimGuard, make_guard
from .typos import apply_typos

__all__ = [
    "PROMPT_VERSION",
    "GuardHit",
    "LLMUserSimulator",
    "ScriptedUserSimulator",
    "SimGuard",
    "SimOutput",
    "apply_typos",
    "build_system_prompt",
    "lenient_sim_output",
    "load_persona_library",
    "make_guard",
    "merge_persona",
    "render_persona",
]
