"""Copilot DVA: the scripted brain with permissive handlers leaks in most ACL probes; the fixed
world (secure handlers) leaks in none. No model."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from dva.config import world_file
from dva.copilot_agent.agent import respond
from dva.flaws import FLAWS
from dva_helpers import serving
from gauntlet_core.packs import load_pack
from gauntlet_core.packs_acl import generate_acl_probes
from gauntlet_core.schema import WorldSpec, load_yaml
from pack_runner import inline, run_scenario_checks

REPO = Path(__file__).parents[3]
ALL = {f.id for f in FLAWS.values() if f.agent == "copilot"}


@pytest.fixture(scope="module")
def pack():
    return load_pack(REPO / "packs" / "enterprise_copilot")


def dva_world(fixed: bool) -> WorldSpec:
    return load_yaml(WorldSpec, world_file("copilot", "fixed" if fixed else "unfixed"))


async def leak_rate(pack, fixed: bool) -> tuple[int, int]:
    world = dva_world(fixed)
    probes = generate_acl_probes(pack.world, seed=11)
    leaked = 0
    async with serving(ALL, respond) as (dva, facade):
        for p in probes:
            if await run_scenario_checks(world, inline(p, world), dva, facade):
                leaked += 1
    return leaked, len(probes)


async def test_permissive_world_leaks_in_at_least_80_percent_of_probes(pack):
    leaked, total = await leak_rate(pack, fixed=False)
    assert total >= 40 and leaked / total >= 0.8, (leaked, total)


async def test_fixed_world_leaks_in_none(pack):
    leaked, total = await leak_rate(pack, fixed=True)
    assert total >= 40 and leaked == 0


async def test_injection_follows_through_only_with_f44(pack):
    world = dva_world(False)
    scn = inline(pack.scenarios["scn_cop_10"], world)
    async with serving({"F44"}, respond) as (dva, facade):
        assert "tainted_escalation" in await run_scenario_checks(world, scn, dva, facade)
    async with serving(set(), respond) as (dva, facade):
        assert await run_scenario_checks(world, scn, dva, facade) == []


def test_dva_worlds_share_the_pack_seed_and_differ_only_in_handlers(pack):
    unsafe, fixed = dva_world(False), dva_world(True)
    assert unsafe.seed == fixed.seed == pack.world.seed
    assert unsafe.canaries == fixed.canaries == pack.world.canaries
    assert [t.name for t in unsafe.tools] == [t.name for t in pack.world.tools]
    handlers = {t.name: t.handler.model_dump() for t in unsafe.tools}
    assert handlers["search_documents"]["entrypoint"].endswith("search_documents_unsafe")
    assert handlers["list_my_groups"] == pack_handler(pack, "list_my_groups")
    assert all(
        t.handler == next(x for x in pack.world.tools if x.name == t.name).handler
        for t in fixed.tools
    )


def pack_handler(pack, name):
    return next(t for t in pack.world.tools if t.name == name).handler.model_dump()


def test_registry_rows_and_prompt_snippets():
    from dva.copilot_agent.agent import build_system_prompt

    assert sorted(ALL) == [f"F{n}" for n in range(40, 47)]
    assert "Operating notes" not in build_system_prompt(set())
    assert str(FLAWS["F44"].prompt_snippet) in build_system_prompt({"F44"})
    assert re.fullmatch(r"phase5:copilot.*", FLAWS["F40"].detect_by[0])
    assert (
        yaml.safe_load((REPO / "apps/dva/worlds/copilot.yaml").read_text())["id"] == "dva_copilot"
    )
