"""Stage 2 of scenario generation, in code only: an outline becomes a `Scenario` with checks
built from it, and is validated."""

from __future__ import annotations

import hashlib
from collections.abc import Collection, Mapping
from typing import Any

from pydantic import ValidationError

from gauntlet_core.schema import Persona, Scenario, WorldSpec
from gauntlet_core.validate import Issue, validate_scenario

from .outline import CallSpec, Outline

__all__ = ["BASE_RUBRICS", "compile_outline", "outline_issues"]

BASE_RUBRICS = ("task_completion", "policy_adherence")


def _call_check(call: CallSpec, **extra: Any) -> dict[str, Any]:
    check: dict[str, Any] = {"type": "tool_called", "tool": call.tool, **extra}
    if call.args:
        check["args"] = {k: {"eq": v} for k, v in call.args.items()}
    return check


def _scenario_id(outline: Outline) -> str:
    digest = hashlib.sha256(f"{outline.title}\n{outline.goal}".encode()).hexdigest()
    return f"scn_gen_{digest[:8]}"


def compile_outline(
    outline: Outline, world: WorldSpec, *, rubric_ids: Collection[str] = ()
) -> Scenario:
    """Raises `ValidationError` when the outline cannot form a valid `Scenario`."""
    parts: list[dict[str, Any]] = [_call_check(c) for c in outline.expected_calls]
    parts += [
        {
            "type": "state",
            "collection": s.collection,
            "id": s.id,
            "path": s.path,
            "matcher": {"eq": s.equals},
        }
        for s in outline.expected_state
    ]
    parts += [
        {"type": "output", "matcher": {"contains": text}}
        for text in outline.expected_output_contains
    ]
    rubrics = [
        *BASE_RUBRICS,
        *(["hallucinated_policy"] if outline.category == "policy_edge" else []),
    ]
    if rubric_ids:
        rubrics = [r for r in rubrics if r in set(rubric_ids)]
    doc = {
        "id": _scenario_id(outline),
        "version": 1,
        "title": outline.title,
        "goal": outline.goal,
        "persona": outline.persona_id,
        "hidden_facts": outline.hidden_facts,
        "world": world.id if world.id else world.model_dump(mode="json"),
        "success": {"type": "all", "of": parts},
        "forbidden": [
            {
                "id": f"forbidden_{i}",
                "description": f"Must not call {c.tool}",
                "severity": "high",
                "check": _call_check(c),
            }
            for i, c in enumerate(outline.forbidden_calls)
        ],
        "rubrics": rubrics,
        "max_turns": 10,
        "tags": {"category": outline.category, "source": "generated"},
    }
    return Scenario.model_validate(doc)


def outline_issues(
    outline: Outline,
    world: WorldSpec,
    personas: Mapping[str, Persona],
    *,
    rubric_ids: Collection[str] = (),
) -> tuple[Scenario | None, list[str]]:
    """The compiled scenario (None when it cannot be built) and the issues as short strings."""
    try:
        scn = compile_outline(outline, world, rubric_ids=rubric_ids)
    except ValidationError as e:
        return None, [f"bad_outline: {err['loc']}: {err['msg']}" for err in e.errors()[:3]]
    issues: list[Issue] = validate_scenario(
        scn,
        world,
        persona_ids=set(personas),
        rubric_ids=set(rubric_ids) if rubric_ids else None,
        strict=True,
    )
    out = [f"{i.code}: {i.message}" for i in issues]
    if not (outline.expected_calls or outline.expected_state or outline.expected_output_contains):
        out.append("no_success_criteria: give at least one expected call, state or output")
    persona = personas.get(outline.persona_id)
    if persona is not None and outline.category == "adversarial" and not persona.adversarial_intent:
        out.append(f"persona_mismatch: {persona.id} is not adversarial")
    return scn, out
