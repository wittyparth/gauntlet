"""Persona rendering and the shipped persona library."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from gauntlet_core.schema import Persona, load_yaml_list

__all__ = ["load_persona_library", "merge_persona", "render_persona"]

LIBRARY_PATH = Path(__file__).parent / "personas" / "library.yaml"


def merge_persona(persona: Persona, overrides: Mapping[str, str | float]) -> Persona:
    """Overrides replace trait values; unknown keys are added."""
    if not overrides:
        return persona
    return persona.model_copy(update={"traits": {**persona.traits, **overrides}})


def _trait(value: str | float) -> str:
    if isinstance(value, float):
        return "low" if value < 0.33 else "medium" if value < 0.66 else "high"
    return str(value)


def render_persona(persona: Persona, overrides: Mapping[str, str | float] | None = None) -> str:
    p = merge_persona(persona, overrides or {})
    lines = [f"Name: {p.name}", f"Description: {p.description}"]
    if p.traits:
        lines.append("Traits:")
        lines += [f"- {k}: {_trait(p.traits[k])}" for k in sorted(p.traits)]
    if p.behavior_rules:
        lines.append("Behaviour rules:")
        lines += [f"- {r}" for r in p.behavior_rules]
    if p.adversarial_intent:
        lines.append(f"Adversarial intent: {p.adversarial_intent}")
    return "\n".join(lines)


def load_persona_library() -> dict[str, Persona]:
    return {p.id: p for p in load_yaml_list(Persona, LIBRARY_PATH)}
