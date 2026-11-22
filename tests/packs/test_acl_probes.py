"""ACL probe generator: deterministic, at least 40 probes, every probe targets a user without
access and a canary that belongs to the document."""

from __future__ import annotations

from pathlib import Path

import pytest
from gauntlet_core.packs import load_pack
from gauntlet_core.packs_acl import generate_acl_probes, write_probes
from gauntlet_core.validate import validate_scenario

PACK_DIR = Path(__file__).parents[2] / "packs" / "enterprise_copilot"


@pytest.fixture(scope="module")
def pack():
    return load_pack(PACK_DIR)


def test_at_least_forty_probes_and_all_validate(pack):
    probes = generate_acl_probes(pack.world, seed=1)
    assert len(probes) >= 40
    assert len({p.id for p in probes}) == len(probes)
    for p in probes:
        assert validate_scenario(p, pack.world, persona_ids=pack.personas, strict=True) == []


def test_same_seed_same_probes_other_seed_differs(pack):
    a = generate_acl_probes(pack.world, seed=1)
    assert [p.model_dump_json() for p in a] == [
        p.model_dump_json() for p in generate_acl_probes(pack.world, seed=1)
    ]
    other = generate_acl_probes(pack.world, seed=2)
    assert [p.opening_message for p in a] != [p.opening_message for p in other]


def test_probes_target_users_without_access_and_the_documents_own_canary(pack):
    docs = {d["id"]: d for d in pack.world.seed["documents"]}
    users = {u["id"]: u for u in pack.world.seed["users"]}
    canary_of = {c.location.split("/")[1]: c.id for c in pack.world.canaries}
    seen_kinds = set()
    for p in generate_acl_probes(pack.world, seed=7):
        seen_kinds.add(p.tags["probe"])
        user = users[p.tags["user"]]
        session = p.world_overrides["session"][0]
        assert session["user_id"] == user["id"] and session["tenant"] == user["tenant"]
        if "document" in p.tags:
            doc = docs[p.tags["document"]]
            assert doc["restricted"]
            can = user["tenant"] == doc["tenant"] and set(user["groups"]) & set(doc["groups"])
            assert not can, p.id
            assert p.forbidden[0].check.canary == canary_of[doc["id"]]  # type: ignore[union-attr]
    assert seen_kinds == {
        "topic", "name", "indirect", "aggregate_count", "aggregate_compare", "cross_tenant",
    }  # fmt: skip


def test_nothing_is_written_unless_asked(pack, tmp_path):
    probes = generate_acl_probes(pack.world, seed=1)
    assert not (PACK_DIR / "scenarios" / "generated").exists()
    paths = write_probes(probes[:3], tmp_path / "gen")
    assert len(paths) == 3 and all(p.read_text().startswith("id: acl_s1_") for p in paths)
