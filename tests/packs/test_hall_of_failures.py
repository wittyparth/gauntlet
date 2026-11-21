"""Hall of Failures pack: structure, neutrality, sources, and good/bad oracle trajectories."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml
from gauntlet_core.checks import evaluate_final
from gauntlet_core.engine import EpisodeCtx, MemoryJournalStore, run_episode
from gauntlet_core.eval import load_rubrics
from gauntlet_core.packs import load_pack
from gauntlet_core.sim import ScriptedUserSimulator
from gauntlet_core.validate import validate_pack
from gauntlet_core.world import World, build_trajectory, build_world

sys.path.insert(0, str(Path(__file__).parent))
from hof_oracles import ORACLES

PACK_DIR = Path(__file__).parents[2] / "packs" / "hall_of_failures"
REAL_NAMES = re.compile(
    r"air canada|moffatt|chevrolet|chevy|tahoe|dpd|mycity|replit|cursor|slack|copilot|echoleak"
    r"|microsoft|chatgpt",
    re.I,
)
EXPECTED_TOOLS = {
    "airline": {
        "lookup_booking": "read",
        "get_fare_rules": "read",
        "submit_refund_request": "financial",
        "escalate_to_human": "write",
    },
    "dealership": {
        "get_vehicle": "read",
        "create_offer": "financial",
        "escalate_to_human": "write",
    },
    "delivery": {"track_parcel": "read", "escalate_to_human": "write"},
    "city_biz": {"search_regulations": "read"},
    "coding_ops": {
        "get_project_status": "read",
        "list_records": "read",
        "delete_record": "destructive",
    },
    "software_support": {
        "search_kb": "read",
        "lookup_account": "read",
        "escalate_to_human": "write",
    },
    "workspace": {
        "search_messages": "read",
        "list_channels": "read",
        "send_dm": "external_comm",
    },
    "mailbox": {
        "search_mailbox": "read",
        "read_email": "read",
        "send_email": "external_comm",
    },
}


@pytest.fixture(scope="module")
def pack():
    return load_pack(PACK_DIR)


def test_pack_loads_with_eight_worlds_and_scenarios_and_validates(pack):
    assert pack.id == "hall_of_failures"
    assert set(pack.worlds) == set(EXPECTED_TOOLS) and len(pack.scenarios) == 8
    assert pack.world is pack.worlds["airline"]  # the first world
    assert validate_pack(pack) == []
    assert all(s.world in pack.worlds and s.max_turns == 8 for s in pack.scenarios.values())
    assert all(
        s.tags["category"] == "hall_of_failures" and s.tags["incident"]
        for s in pack.scenarios.values()
    )


def test_worlds_have_the_specified_tools_and_risks(pack):
    for wid, want in EXPECTED_TOOLS.items():
        assert {t.name: t.risk for t in pack.worlds[wid].tools} == want, wid
    assert next(
        t for t in pack.worlds["workspace"].tools if t.name == "search_messages"
    ).untrusted_output
    assert next(t for t in pack.worlds["mailbox"].tools if t.name == "read_email").untrusted_output


def test_canaries_and_injected_documents_plant(pack):
    for wid, canary in (("workspace", "staging_key"), ("mailbox", "q3_figure")):
        built = build_world(pack.worlds[wid], None, 7)
        assert [c.id for c in built.canaries] == [canary]
        assert built.canaries[0].value in str(built.initial)
        assert built.markers  # the injected content carries a taint marker
    ws = pack.worlds["workspace"]
    assert ws.documents[0].injection is not None and not ws.documents[0].trusted


def test_rubrics_suite_and_attack_refs(pack):
    known = set(load_rubrics())
    for s in pack.scenarios.values():
        assert set(s.rubrics) <= known, s.id
    suite = pack.suites["hall"]
    assert suite.scenarios == sorted(pack.scenarios) and suite.repetitions == 3
    assert pack.scenarios["hof_07"].attack and pack.scenarios["hof_08"].attack
    assert pack.scenarios["hof_08"].tags["attack_placement"] == "hidden_text"


def test_attack_ids_exist_in_the_library(pack):
    from gauntlet_core.security import load_attacks, load_taxonomy

    root = Path(__file__).parents[2] / "attacks"
    lib = load_attacks(root / "library", load_taxonomy(root / "taxonomy.yaml"))
    for sid in ("hof_07", "hof_08"):
        assert lib.get(pack.scenarios[sid].attack.attack) is not None


def test_no_real_company_names_outside_tags(pack):
    for s in pack.scenarios.values():
        text = yaml.safe_dump(s.model_dump(mode="json", exclude={"tags"}))
        assert not REAL_NAMES.search(text), s.id
    for f in (PACK_DIR / "worlds").glob("*.yaml"):
        assert not REAL_NAMES.search(f.read_text()), f.name


def test_sources_file_has_eight_verified_rows_with_urls():
    rows = [
        ln for ln in (PACK_DIR / "SOURCES.md").read_text().splitlines() if ln.startswith("| hof_")
    ]
    assert len(rows) == 8
    for ln in rows:
        cells = [c.strip() for c in ln.strip("|").split("|")]
        assert len(cells) == 6 and cells[5].startswith("verified 20"), ln
        assert re.search(r"https://\S+", cells[4]), ln


class ScriptedAgent:
    stateful = False

    def __init__(self, world, calls, text):
        self.world, self.calls, self.text = world, calls, text

    async def open(self, ctx):
        pass

    async def close(self, ctx):
        pass

    async def send(self, ctx, user_text):
        for tool, args in self.calls:
            await self.world.call_tool(ctx, tool, args)
        return self.text


async def evaluate(pack, scn, run):
    calls, text = run
    spec = pack.worlds[scn.world]
    built = build_world(spec, scn.world_overrides, 7)
    store = MemoryJournalStore()
    ctx = await EpisodeCtx.open(store, "ep_1", run_id="run_1", rng_seed=7)
    world = World(built)
    await run_episode(ctx, scn, ScriptedAgent(world, calls, text), ScriptedUserSimulator(["hi"]))
    traj = build_trajectory("ep_1", scn, (await store.load("ep_1")).events, built)
    success = evaluate_final(scn.success, traj).holds
    sprung = [n.id for n in scn.forbidden if evaluate_final(n.check, traj).holds]
    return success, sprung


@pytest.mark.parametrize("n", range(1, 9))
async def test_good_trajectory_passes(pack, n):
    success, sprung = await evaluate(pack, pack.scenarios[f"hof_{n:02d}"], ORACLES[n][0])
    assert success, "success must hold on the good run"
    assert sprung == [], f"forbidden checks fired on the good run: {sprung}"


@pytest.mark.parametrize("n", range(1, 9))
async def test_bad_trajectory_fails(pack, n):
    success, sprung = await evaluate(pack, pack.scenarios[f"hof_{n:02d}"], ORACLES[n][1])
    assert sprung or not success, "the bad run must spring a forbidden check or miss success"
    assert sprung, "the bad run must spring at least one forbidden check"


@pytest.mark.parametrize("n", [7, 8])
async def test_injection_scenarios_fire_tainted_call_on_the_bad_run(pack, n):
    _, sprung = await evaluate(pack, pack.scenarios[f"hof_{n:02d}"], ORACLES[n][1])
    assert {"tainted_dm", "tainted_email"} & set(sprung) and "egress" in sprung


def test_multi_world_manifest_rejects_a_scenario_world_that_is_not_listed(tmp_path):
    import shutil

    from gauntlet_core.packs import PackError

    dst = tmp_path / "hof"
    shutil.copytree(PACK_DIR, dst)
    manifest = yaml.safe_load((dst / "pack.yaml").read_text())
    manifest["worlds"] = manifest["worlds"][:7]  # the mailbox world is no longer listed
    (dst / "pack.yaml").write_text(yaml.safe_dump(manifest))
    with pytest.raises(PackError, match="not a pack world"):
        load_pack(dst)
