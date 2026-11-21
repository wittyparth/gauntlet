"""The injection harness (hard-cores 6.2, 6.3): put an attack payload where its vector says.

`place` is pure. It never touches a model and never mutates its inputs. The benign user goal
stays the scenario goal, so one episode measures both "was the agent hijacked" (the objective,
added as a forbidden check with id `objective`) and "did it still do the user's task"
(the scenario's own `success`).

Where a payload goes, by vector (`Attack.target` names the place):
* `document`: the document with that id (default: the first document), styled by the
  `+embed:<placement>` marker in `technique` (CQ-S1), appended to the body. The document is
  marked untrusted.
* `tool_result`: `target` is a tool name (an `inject:<tool>` document whose body is appended to
  every result of that tool) or `collection/id/field` (the record field is overwritten through
  `world_overrides`, and the tools that read that collection are marked `untrusted_output`).
* `tool_description`: appended to the named tool's description.
* `user_turn`: the payload turns become the scripted user turns (`tags["attack_turns"]`).
`system_context` is not placeable in Phase 2 (it needs the target config) and raises.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, NamedTuple

from gauntlet_core.schema import (
    Attack,
    AttackRef,
    CrudHandler,
    DocumentSpec,
    InjectionSpec,
    Json,
    NamedCheck,
    Scenario,
    WorldSpec,
)
from gauntlet_core.world.markers import INJECT_PREFIX

from .hardening import harden_objective, is_informational
from .library import payload_texts
from .placeholders import PLACEHOLDER_RE, is_allowed_placeholder, substitute

__all__ = [
    "PLACED_TAG",
    "TURNS_TAG",
    "Placed",
    "PlacementError",
    "apply_style",
    "make_marker",
    "place",
    "placement_style",
]

PLACED_TAG = "placed"
TURNS_TAG = "attack_turns"
_EMBED_RE = re.compile(r"\+embed:(body|footer|html_comment|hidden_text|metadata)")


class PlacementError(ValueError):
    """The attack cannot be placed in this world or scenario."""


class Placed(NamedTuple):
    world: WorldSpec
    scenario: Scenario
    markers: tuple[str, ...]


def make_marker(seed: int, attack_id: str, n: int = 0) -> str:
    """A unique high-entropy token, stable for (seed, attack id): `gmk-` plus 12 hex digits."""
    digest = hashlib.sha256(f"{seed}:{attack_id}:{n}".encode()).hexdigest()
    return f"gmk-{digest[:12]}"


def placement_style(attack: Attack) -> str:
    m = _EMBED_RE.search(attack.technique)
    return m.group(1) if m else "body"


def apply_style(text: str, style: str) -> str:
    """How an injected payload is dressed inside the carrier (a pure string transform)."""
    if style == "body":
        return text
    if style == "footer":
        return f"-- \n{text}"
    if style == "html_comment":
        return f"<!-- {text} -->"
    if style == "hidden_text":
        return f'<span style="display:none">{text}</span>'
    if style == "metadata":
        return json.dumps({"note": text})
    raise PlacementError(f"unknown placement style {style!r}")


def _values(attack: Attack, world: WorldSpec, scenario: Scenario, marker: str) -> dict[str, str]:
    values = {
        "marker": marker,
        "attacker_email": f"{marker}@attacker.example",
        "attacker_url": f"https://{marker}.attacker.example/c",
        "user_goal": scenario.goal,
    }
    honey = next((t.name for t in world.tools if t.honeytool), None)
    if honey is not None:
        values["honeytool"] = honey
    for c in world.canaries:  # the attacker knows where a secret lives, never its value
        values[f"canary:{c.id}"] = c.location
    return values


def _resolve(text: str, values: dict[str, str], what: str) -> str:
    for name in PLACEHOLDER_RE.findall(text):
        if not is_allowed_placeholder(name):
            raise PlacementError(f"{what}: unknown placeholder {{{{{name}}}}}")
        if name not in values:
            raise PlacementError(f"{what}: placeholder {{{{{name}}}}} has no value in this world")
    return substitute(text, values)


def _walk(obj: Any, fn: Any) -> Any:
    if isinstance(obj, str):
        return fn(obj)
    if isinstance(obj, list):
        return [_walk(v, fn) for v in obj]
    if isinstance(obj, dict):
        return {k: _walk(v, fn) for k, v in obj.items()}
    return obj


def _mark_untrusted(tools: list, names: set[str]) -> list:
    return [
        t.model_copy(update={"untrusted_output": True}) if t.name in names else t for t in tools
    ]


def _record_field(
    world: WorldSpec, scenario: Scenario, target: str, text: str
) -> tuple[WorldSpec, Json]:
    collection, rid, fld = target.split("/", 2)
    overrides: Json = {c: [dict(r) for r in recs] for c, recs in scenario.world_overrides.items()}
    recs = overrides.setdefault(collection, [])
    rec = next((r for r in recs if str(r["id"]) == rid), None)
    if rec is None:
        base = next((r for r in world.seed.get(collection, []) if str(r["id"]) == rid), None)
        if base is None:
            raise PlacementError(f"no record {collection}/{rid} in the world")
        rec = {"id": rid, fld: base.get(fld, "")}
        recs.append(rec)
    existing = rec.get(fld)
    rec[fld] = f"{existing}\n{text}" if isinstance(existing, str) and existing else text
    readers = {
        t.name
        for t in world.tools
        if isinstance(t.handler, CrudHandler) and t.handler.collection == collection
    }
    if not readers:
        raise PlacementError(
            f"no tool reads collection {collection!r}; the payload would be unseen"
        )
    return world.model_copy(
        update={"tools": _mark_untrusted(list(world.tools), readers)}
    ), overrides


def place(
    attack: Attack,
    world: WorldSpec,
    scenario: Scenario,
    *,
    seed: int = 0,
    doc_body: str | None = None,
) -> Placed:
    """Return `(world', scenario', markers)`. `doc_body` replaces the target document's body
    before the payload is added (the shrinker uses it to remove surrounding content)."""
    marker = make_marker(seed, attack.id)
    values = _values(attack, world, scenario, marker)
    turns = [_resolve(t, values, f"attack {attack.id}") for t in payload_texts(attack)]
    text = "\n".join(turns)
    style = placement_style(attack)
    tags = {
        **scenario.tags,
        PLACED_TAG: "true",
        "attack_category": attack.category,
        "attack_vector": attack.vector,
    }
    update: dict[str, Any] = {}

    if attack.vector == "document":
        docs = list(world.documents)
        doc = next((d for d in docs if d.id == attack.target), None) if attack.target else None
        if doc is None and attack.target is None and docs:
            doc = docs[0]
        if doc is None:
            raise PlacementError(f"no document {attack.target!r} in the world")
        base = doc.body if doc_body is None else doc_body
        body = f"{base}\n\n{apply_style(text, style)}".strip()
        new = DocumentSpec(
            id=doc.id,
            title=doc.title,
            body=body,
            trusted=False,
            injection=InjectionSpec(attack=attack.id, placement=style),  # type: ignore[arg-type]
        )
        world = world.model_copy(update={"documents": [new if d.id == doc.id else d for d in docs]})
    elif attack.vector == "tool_result":
        if attack.target is None:
            raise PlacementError(
                "a tool_result attack needs a target (tool or collection/id/field)"
            )
        styled = apply_style(text, style)
        if "/" in attack.target:
            world, overrides = _record_field(world, scenario, attack.target, styled)
            update["world_overrides"] = overrides
        else:
            if attack.target not in {t.name for t in world.tools}:
                raise PlacementError(f"no tool {attack.target!r} in the world")
            did = f"{INJECT_PREFIX}{attack.target}"
            inj = DocumentSpec(
                id=did,
                title=f"injected result of {attack.target}",
                body=styled,
                trusted=False,
                injection=InjectionSpec(attack=attack.id, placement=style),  # type: ignore[arg-type]
            )
            docs = [d for d in world.documents if d.id != did] + [inj]
            tools = _mark_untrusted(list(world.tools), {attack.target})
            world = world.model_copy(update={"documents": docs, "tools": tools})
    elif attack.vector == "tool_description":
        tool = next((t for t in world.tools if t.name == attack.target), None)
        if tool is None:
            raise PlacementError(f"no tool {attack.target!r} in the world")
        edited = tool.model_copy(update={"description": f"{tool.description}\n{text}"})
        world = world.model_copy(
            update={"tools": [edited if t.name == tool.name else t for t in world.tools]}
        )
    elif attack.vector == "user_turn":
        tags[TURNS_TAG] = json.dumps(turns)
        update["opening_message"] = turns[0]
    else:
        raise PlacementError(f"vector {attack.vector!r} is not placeable in Phase 2")

    # exclude_none: library files carry explicit `eq: null` matcher fields, which the matcher
    # treats as "equals null" and so never match; dropping nulls restores "operator not set"
    objective = _walk(
        attack.objective.model_dump(mode="json", exclude_none=True),
        lambda s: _resolve(s, values, "objective"),
    )
    informational = is_informational(objective)
    if informational:
        tags["informational"] = "true"  # echo objective: recorded, never a finding
    objective = harden_objective(objective, world, marker)
    named = NamedCheck.model_validate(
        {
            "id": "informational" if informational else "objective",
            "description": attack.title,
            "severity": attack.severity,
            "check": objective,
        }
    )
    placed = scenario.model_copy(
        update={
            **update,
            "id": f"{scenario.id}+{attack.id}",
            "world": world,
            "tags": tags,
            "attack": AttackRef(attack=attack.id),
            "forbidden": [f for f in scenario.forbidden if f.id not in ("objective", named.id)]
            + [named],
        }
    )
    used = tuple(m for m in (marker,) if m in text or m in json.dumps(objective))
    return Placed(world, placed, used)
