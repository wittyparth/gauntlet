"""`--fake-llm FILE.yaml`: the scripted gateway lives in core (the dev server uses it too)."""

from __future__ import annotations

from gauntlet_core.llm.scripted import ScriptedLLM, load_scripted_llm

load_fake_llm = load_scripted_llm

__all__ = ["ScriptedLLM", "load_fake_llm"]
