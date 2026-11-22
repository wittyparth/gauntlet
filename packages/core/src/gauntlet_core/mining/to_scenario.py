"""Conversation to draft scenario (P5-2). Fails closed: a scenario with anything personal left in
it is never produced."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from gauntlet_core.llm import Gateway
from gauntlet_core.llm.types import GatewayError, StructuredOutputError
from gauntlet_core.schema import Cost, Event, Scenario, WorldSpec
from gauntlet_core.validate import validate_scenario

from .anonymise import Anonymised, Residual, anonymise, residual_scan
from .prompts import scenario_messages
from .world_from_trace import world_from_trace

__all__ = ["ConversionFailed", "MinedDraft", "ScenarioDraft", "to_scenario"]

DEFAULT_PERSONA = "per_cooperative"


class ConversionFailed(Exception):
    """`reasons` name kinds of problems (never values)."""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


class ScenarioDraft(BaseModel):
    title: str = Field(max_length=120)
    goal: str
    hidden_facts: list[str] = Field(default_factory=list, max_length=6)
    opening_message: str | None = None


@dataclass
class MinedDraft:
    scenario: Scenario
    needs_review: list[str]
    notes: list[str] = field(default_factory=list)
    cost: Cost = field(default_factory=Cost)


def _scenario_id(conv_ref: str, seed: int) -> str:
    return "scn_mined_" + hashlib.sha256(f"{conv_ref}:{seed}".encode()).hexdigest()[:10]


def _success_and_notes(
    events: Sequence[Event], world: WorldSpec
) -> tuple[dict[str, Any], list[str], list[str]]:
    known = {t.name: t for t in world.tools}
    used: list[str] = []
    notes: list[str] = []
    for e in events:
        if e.kind == "tool_result" and e.payload.get("ok"):
            call = next(
                (c for c in events if c.kind == "tool_call"
                 and c.payload.get("call_id") == e.payload.get("call_id")), None,
            )  # fmt: skip
            tool = str(call.payload.get("tool")) if call else None
            if tool and tool in known and tool not in used:
                used.append(tool)
            elif tool and tool not in known:
                notes.append(f"tool {tool} is not in the agent's world and was left out")
    writes = [t for t in used if known[t].risk != "read"]
    pick = writes or used
    parts: list[dict[str, Any]] = [{"type": "tool_called", "tool": t, "ok": True} for t in pick]
    parts.append({"type": "output", "matcher": {"exists": True}})
    review = ["success: inferred from tool names only (arguments and state were not checked)"]
    if not pick:
        review.append("success: the trace shows no tool resolving the request")
    return {"type": "all", "of": parts}, review, notes


async def to_scenario(
    events: Sequence[Event],
    *,
    conv_ref: str,
    world: WorldSpec,
    gateway: Gateway,
    seed: int,
    detector_hits: Sequence[str] = (),
    persona_ids: Sequence[str] = (DEFAULT_PERSONA,),
    anonymised: Anonymised | None = None,
) -> MinedDraft:
    """`events` are the stored (redacted) events; anonymisation is repeated here."""
    anon = anonymised or anonymise(events, seed=seed)
    if anon.residual:
        raise ConversionFailed(sorted({r.kind for r in anon.residual}))
    try:
        res = await gateway.complete(
            "generator", scenario_messages(anon.events), response_model=ScenarioDraft,
            temperature=0.0, seed=seed,
        )  # fmt: skip
    except (StructuredOutputError, GatewayError) as e:
        raise ConversionFailed([f"model: {type(e).__name__}"]) from e
    draft = res.parsed
    if not isinstance(draft, ScenarioDraft):
        raise ConversionFailed(["model: no structured output"])
    overrides, unmapped = world_from_trace(anon.events, world)
    success, review, notes = _success_and_notes(anon.events, world)
    forbidden = [
        {
            "id": f"mined_{name}",
            "description": f"the {name} detector fired on the production conversation",
            "severity": "high" if name in ("secret", "markdown_image_exfil") else "medium",
            "check": {"type": "detector", "name": name},
        }
        for name in detector_hits
    ]
    persona = DEFAULT_PERSONA if DEFAULT_PERSONA in persona_ids else sorted(persona_ids)[0]
    try:
        scenario = Scenario.model_validate(
            {
                "id": _scenario_id(conv_ref, seed),
                "title": draft.title,
                "goal": draft.goal,
                "persona": persona,
                "hidden_facts": draft.hidden_facts,
                "opening_message": draft.opening_message,
                "world": world.id if world.id else world.model_dump(mode="json"),
                "world_overrides": overrides,
                "success": success,
                "forbidden": forbidden,
                "tags": {"mined_from": conv_ref, "source": "mined"},
            }
        )
    except ValidationError as e:
        raise ConversionFailed([f"scenario: {e.errors()[0]['type']}"]) from e
    issues = [i for i in validate_scenario(scenario, world, persona_ids=set(persona_ids)) if i.code]
    if issues:
        raise ConversionFailed([f"validation: {i.code}" for i in issues])
    # Post-check: the model could have reintroduced something. Scan every free-text field.
    texts = [scenario.title, scenario.goal, scenario.opening_message or "", *scenario.hidden_facts]
    texts += _strings(scenario.world_overrides)
    leftover: list[Residual] = residual_scan(texts, allow=anon.synthetic)
    if leftover:
        raise ConversionFailed(sorted({r.kind for r in leftover}))
    if unmapped:
        notes.append("tools whose results could not seed the world: " + ", ".join(unmapped))
    return MinedDraft(scenario, review, notes, res.cost)


def _strings(v: Any) -> list[str]:
    if isinstance(v, str):
        return [v]
    if isinstance(v, dict):
        return [s for x in v.values() for s in _strings(x)]
    if isinstance(v, list):
        return [s for x in v for s in _strings(x)]
    return []
