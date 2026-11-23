"""Enterprise copilot pack: structure, policy references, secure handlers, and good/bad oracles."""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from gauntlet_core.checks import evaluate_final
from gauntlet_core.engine import EpisodeCtx, MemoryJournalStore, run_episode
from gauntlet_core.eval import load_rubrics
from gauntlet_core.packs import load_pack
from gauntlet_core.sim import ScriptedUserSimulator
from gauntlet_core.validate import validate_pack
from gauntlet_core.world import (
    World,
    WorldState,
    WorldView,
    assert_pure,
    build_trajectory,
    build_world,
)

sys.path.insert(0, str(Path(__file__).parent))
from cop_oracles import ORACLES

CODE = "from packs.enterprise_copilot import gen_seed as g; print(g.render())"
PACK_DIR = Path(__file__).parents[2] / "packs" / "enterprise_copilot"


@pytest.fixture(scope="module")
def pack():
    return load_pack(PACK_DIR)


def test_pack_loads_validates_and_has_twenty_scenarios(pack):
    assert pack.id == "enterprise_copilot" and pack.world.id == "enterprise_copilot"
    assert [t.name for t in pack.world.tools] == [
        "search_documents",
        "get_document",
        "list_my_groups",
        "search_messages",
        "escalate_to_human",
    ]
    assert sorted(pack.scenarios) == [f"scn_cop_{i:02d}" for i in range(1, 21)]
    assert validate_pack(pack) == []
    rubrics = set(load_rubrics())
    for s in pack.scenarios.values():
        assert s.persona in pack.personas and set(s.rubrics) <= rubrics and s.hidden_facts
        assert s.world == "enterprise_copilot" and "session" in s.world_overrides


def test_policy_clause_ids_resolve(pack):
    clauses = set(re.findall(r"\((C\d+)\)", pack.policy_text))
    assert clauses == {f"C{i}" for i in range(1, 11)}
    assert {s.tags["policy"] for s in pack.scenarios.values()} <= clauses


def test_seed_regenerates_byte_identical():
    from packs.enterprise_copilot import gen_seed

    assert gen_seed.SEED_PATH.read_text() == gen_seed.render()
    out = subprocess.run(
        [sys.executable, "-c", CODE],
        capture_output=True,
        text=True,
        check=True,
        cwd=gen_seed.SEED_PATH.parents[2],
    ).stdout
    assert out.rstrip("\n") == gen_seed.SEED_PATH.read_text().rstrip("\n")


def test_every_restricted_record_has_its_own_canary(pack):
    for d in pack.world.seed["documents"]:
        has = [c for c in pack.world.canaries if c.location == f"documents/{d['id']}/access_code"]
        assert bool(has) == bool(d["restricted"]), d["id"]
    assert len({c.id for c in pack.world.canaries}) == len(pack.world.canaries)


NOW = datetime(2026, 3, 15, 10, tzinfo=UTC)


def _session(pack, user):
    u = next(x for x in pack.world.seed["users"] if x["id"] == user)
    return {
        "session": [
            {"id": "current", "user_id": u["id"], "groups": u["groups"], "tenant": u["tenant"]}
        ]
    }


def _state(pack, user):
    return WorldState.from_seed(pack.world.seed | _session(pack, user))


def test_secure_handlers_filter_by_session_acl_and_tenant(pack):
    from packs.enterprise_copilot import handlers as h

    def run(user, fn, **args):
        view = WorldView(_state(pack, user))
        assert_pure(fn, view, dict(args), NOW)
        return fn(view, dict(args), NOW)

    assert run("u_dan", h.get_document, document_id="doc_a08").result["id"] == "doc_a08"
    for user, doc in (("u_ben", "doc_a06"), ("u_eli", "doc_a04"), ("u_fay", "doc_a06")):
        assert run(user, h.get_document, document_id=doc).error == "not_found"
    assert run("u_ana", h.get_document, document_id="doc_zzz").error == "not_found"
    found = run("u_ben", h.search_documents, query="layoffs headcount reduction").result
    assert all(r["id"] != "doc_a06" for r in found)
    mgmt = run("u_dan", h.search_documents, query="layoffs headcount reduction").result
    assert mgmt and mgmt[0]["id"] == "doc_a06"
    assert run("u_eli", h.search_documents, query="holidays").result == []
    assert run("u_ben", h.list_my_groups).result["groups"] == ["g_all", "g_sales"]
    texts = [m["text"] for m in run("u_ben", h.search_messages, query="salary adjustment").result]
    assert not any("Salary adjustment" in t for t in texts)


def test_search_prefers_the_current_document_and_flags_the_superseded(pack):
    from packs.enterprise_copilot import handlers as h

    view = WorldView(_state(pack, "u_ben"))
    rows = h.search_documents(view, {"query": "pricing discount"}, NOW).result
    assert {"doc_a09", "doc_a10"} <= {r["id"] for r in rows}
    assert next(r for r in rows if r["id"] == "doc_a09")["superseded_by"] == "doc_a10"


async def evaluate(pack, scn, run):
    calls, text = run
    built = build_world(pack.world, scn.world_overrides, 7)
    values = {c.id: c.value for c in built.canaries}
    text = text.format_map(values)
    store = MemoryJournalStore()
    ctx = await EpisodeCtx.open(store, "ep_1", run_id="run_1", rng_seed=7)
    ctx.clock_start = pack.world.clock_start
    world = World(built)

    class Agent:
        stateful = False

        async def open(self, ctx):
            pass

        async def close(self, ctx):
            pass

        async def send(self, ctx, user_text):
            for tool, args in calls:
                await world.call_tool(ctx, tool, args)
            return text

    await run_episode(ctx, scn, Agent(), ScriptedUserSimulator(["hi"]))
    traj = build_trajectory("ep_1", scn, (await store.load("ep_1")).events, built)
    success = evaluate_final(scn.success, traj).holds
    sprung = [n.id for n in scn.forbidden if evaluate_final(n.check, traj).holds]
    return success, sprung


@pytest.mark.parametrize("n", range(1, 21))
async def test_good_trajectory_passes(pack, n):
    success, sprung = await evaluate(pack, pack.scenarios[f"scn_cop_{n:02d}"], ORACLES[n][0])
    assert success, "success must hold on the good run"
    assert sprung == [], f"forbidden checks fired on the good run: {sprung}"


@pytest.mark.parametrize("n", range(1, 21))
async def test_bad_trajectory_fails(pack, n):
    scn = pack.scenarios[f"scn_cop_{n:02d}"]
    _, sprung = await evaluate(pack, scn, ORACLES[n][1])
    assert sprung, "the bad run must spring at least one forbidden check"
