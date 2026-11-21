"""One test per issue code of `validate_scenario`, mutating a valid ecommerce scenario."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from gauntlet_core.eval.rubrics import load_rubrics
from gauntlet_core.packs import load_pack
from gauntlet_core.validate import validate_scenario

REPO = Path(__file__).parents[3]


@pytest.fixture(scope="module")
def pack():
    return load_pack(REPO / "packs" / "ecommerce")


def codes(pack, scn, **kw: Any) -> set[str]:
    kw.setdefault("persona_ids", set(pack.personas))
    kw.setdefault("rubric_ids", set(load_rubrics()))
    return {i.code for i in validate_scenario(scn, pack.world, **kw)}


def test_every_pack_scenario_is_valid_even_strict(pack):
    for scn in pack.scenarios.values():
        assert codes(pack, scn, strict=True) == set(), scn.id


def test_unknown_persona(pack):
    scn = pack.scenarios["scn_ecom_01"].model_copy(update={"persona": "per_nobody"})
    assert codes(pack, scn) == {"unknown_persona"}


def test_unknown_tool(pack):
    check = {"type": "tool_called", "tool": "teleport"}
    scn = pack.scenarios["scn_ecom_01"].model_validate(
        {**pack.scenarios["scn_ecom_01"].model_dump(mode="json"), "success": check}
    )
    assert codes(pack, scn) == {"unknown_tool"}


def mutated(pack, **updates: Any):
    base = pack.scenarios["scn_ecom_01"].model_dump(mode="json")
    return type(pack.scenarios["scn_ecom_01"]).model_validate({**base, **updates})


def test_unknown_collection_and_record(pack):
    st = {"type": "state", "collection": "ghosts", "id": "g1", "path": "x", "matcher": {"eq": 1}}
    assert codes(pack, mutated(pack, success=st)) == {"unknown_collection"}
    st = {**st, "collection": "orders", "id": "ord_9999"}
    assert codes(pack, mutated(pack, success=st)) == {"unknown_record"}


def test_state_record_added_by_overrides_is_known(pack):
    st = {"type": "state", "collection": "orders", "id": "ord_9999", "path": "status",
          "matcher": {"eq": "x"}}  # fmt: skip
    scn = mutated(pack, success=st, world_overrides={"orders": [{"id": "ord_9999"}]})
    assert codes(pack, scn) == set()


def test_unknown_ref_collection(pack):
    check = {
        "type": "tool_called",
        "tool": "issue_refund",
        "args": {"amount_cents": {"ref": "world:ghosts/{args.order_id}/total", "ref_op": "gt"}},
    }
    assert codes(pack, mutated(pack, success=check)) == {"unknown_ref_collection"}


def test_unknown_rubric(pack):
    assert codes(pack, mutated(pack, rubrics=["task_completion", "vibes"])) == {"unknown_rubric"}


def test_unknown_world_and_inline_world(pack):
    assert codes(pack, mutated(pack, world="elsewhere")) == {"unknown_world"}
    inline = pack.world.model_dump(mode="json")
    assert codes(pack, mutated(pack, world=inline)) == set()


def test_unknown_detector_and_judge_check(pack):
    det = {"type": "detector", "name": "vibes"}
    assert codes(pack, mutated(pack, success=det)) == {"unknown_detector"}
    judge = {"type": "judge", "rubric": "task_completion"}
    assert codes(pack, mutated(pack, success=judge)) == {"judge_check_unsupported"}


def test_strict_rules_empty_hidden_facts_and_max_turns(pack):
    scn = mutated(pack, hidden_facts=[])
    assert codes(pack, scn) == set()
    assert codes(pack, scn, strict=True) == {"empty_hidden_facts"}
    broken = pack.scenarios["scn_ecom_01"].model_construct(
        **{**pack.scenarios["scn_ecom_01"].__dict__, "max_turns": 500}
    )
    assert codes(pack, broken, strict=True) == {"bad_max_turns"}


def test_attack_with_inline_world_requires_placed_tag():
    from gauntlet_core.schema import AttackRef, Scenario, WorldSpec

    world = WorldSpec(tools=[], seed={}, clock_start="2026-01-01T00:00:00Z")  # type: ignore[arg-type]
    base = {
        "id": "s1", "title": "t", "goal": "g", "persona": "p", "world": world,
        "success": {"type": "output", "matcher": {"contains": "x"}},
        "attack": AttackRef(attack="atk_x"),
    }  # fmt: skip
    bad = validate_scenario(Scenario.model_validate(base), world)
    assert [i.code for i in bad] == ["attack_inline_world"]
    ok = validate_scenario(Scenario.model_validate({**base, "tags": {"placed": "true"}}), world)
    assert ok == []
