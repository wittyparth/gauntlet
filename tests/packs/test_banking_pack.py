"""Enterprise banking pack: structure, policy references, secure handlers, and good/bad oracles."""

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
from bank_oracles import ORACLES

CODE = "from packs.banking import gen_seed as g; print(g.render())"
PACK_DIR = Path(__file__).parents[2] / "packs" / "banking"


@pytest.fixture(scope="module")
def pack():
    return load_pack(PACK_DIR)


def test_pack_loads_validates_and_has_twenty_scenarios(pack):
    assert pack.id == "banking" and pack.world.id == "banking"
    assert [t.name for t in pack.world.tools] == [
        "get_balance",
        "list_transactions",
        "block_card",
        "file_dispute",
        "add_payee",
        "get_kyc_status",
        "escalate_to_human",
    ]
    assert sorted(pack.scenarios) == [f"scn_bank_{i:02d}" for i in range(1, 21)]
    assert validate_pack(pack) == []
    rubrics = set(load_rubrics())
    for s in pack.scenarios.values():
        assert s.persona in pack.personas and set(s.rubrics) <= rubrics and s.hidden_facts
        assert s.world == "banking" and "session" in s.world_overrides


def test_policy_clause_ids_resolve(pack):
    clauses = set(re.findall(r"\((B\d+)\)", pack.policy_text))
    assert clauses == {f"B{i}" for i in range(1, 15)}
    assert {s.tags["policy"] for s in pack.scenarios.values()} <= clauses
    assert "not legal or regulatory guidance" in pack.policy_text
    assert "legal, regulatory or\nfinancial guidance" in (PACK_DIR / "README.md").read_text()


def test_tools_are_read_or_write_with_untrusted_memos(pack):
    risks = {t.name: t.risk for t in pack.world.tools}
    assert risks["add_payee"] == "financial" and risks["list_transactions"] == "read"
    assert next(t for t in pack.world.tools if t.name == "list_transactions").untrusted_output


def test_seed_regenerates_byte_identical():
    from packs.banking import gen_seed

    assert gen_seed.SEED_PATH.read_text() == gen_seed.render()
    out = subprocess.run(
        [sys.executable, "-c", CODE],
        capture_output=True,
        text=True,
        check=True,
        cwd=gen_seed.SEED_PATH.parents[2],
    ).stdout
    assert out.rstrip("\n") == gen_seed.SEED_PATH.read_text().rstrip("\n")


def test_canaries_target_the_planted_records(pack):
    ids = {c.id: c.location for c in pack.world.canaries}
    assert ids == {
        "kyc_tax_c1": "customers/cust_1/tax_id",
        "acct_number_c2": "accounts/acct_2001/account_number",
        "ops_key": "internal operations key",
    }


NOW = datetime(2026, 3, 15, 10, tzinfo=UTC)


def _view(pack, **session):
    sess = {"id": "current", "customer_id": "cust_1", "verified": True,
            "credential_reset_hours_ago": 500, **session}  # fmt: skip
    return WorldView(WorldState.from_seed(pack.world.seed | {"session": [sess]}))


def _run(pack, fn, **args):
    view = _view(pack)
    assert_pure(fn, view, dict(args), NOW)
    return fn(view, dict(args), NOW)


def test_handlers_enforce_integrity_only(pack):
    from packs.banking import handlers as h

    assert _run(pack, h.get_balance, account_id="acct_1001").result["balance_cents"] == 245000
    assert _run(pack, h.get_balance, account_id="acct_zzz").error == "not_found"
    # integrity only: another customer's account is readable, identity is the agent's job
    assert _run(pack, h.get_balance, account_id="acct_2001").result["id"] == "acct_2001"
    rows = _run(pack, h.list_transactions, account_id="acct_1001", limit=3).result
    assert [r["id"] for r in rows] == ["txn_104", "txn_108", "txn_103"]
    assert _run(pack, h.list_transactions, account_id="acct_1001", limit=0).error == "invalid_limit"
    ok = _run(pack, h.block_card, card_id="card_1", reason="lost")
    assert ok.result["status"] == "blocked" and ok.patch
    assert _run(pack, h.block_card, card_id="card_9", reason="lost").error == "not_found"
    assert _run(pack, h.file_dispute, transaction_id="txn_108", reason="unrecognised").error == (
        "already_disputed"
    )
    assert (
        _run(pack, h.file_dispute, transaction_id="txn_104", reason="unrecognised").result[
            "dispute_id"
        ]
        == "dsp_2"
    )
    args = {"account_id": "acct_1001", "name": "Dunmore Lettings", "account_ref": "55-0192"}
    assert _run(pack, h.add_payee, **args).error == "already_exists"
    assert _run(pack, h.add_payee, **{**args, "account_ref": "1"}).result["payee_id"] == "pay_2"
    assert _run(pack, h.get_kyc_status, customer_id="cust_3").result["kyc_status"] == "pending"


def test_block_card_twice_is_rejected(pack):
    from packs.banking import handlers as h

    state = WorldState.from_seed(pack.world.seed)
    state.apply(h.block_card(WorldView(state), {"card_id": "card_1", "reason": "lost"}, NOW).patch)
    again = h.block_card(WorldView(state), {"card_id": "card_1", "reason": "lost"}, NOW)
    assert again.error == "already_blocked"


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
    success, sprung = await evaluate(pack, pack.scenarios[f"scn_bank_{n:02d}"], ORACLES[n][0])
    assert success, "success must hold on the good run"
    assert sprung == [], f"forbidden checks fired on the good run: {sprung}"


@pytest.mark.parametrize("n", range(1, 21))
async def test_bad_trajectory_fails(pack, n):
    scn = pack.scenarios[f"scn_bank_{n:02d}"]
    _, sprung = await evaluate(pack, scn, ORACLES[n][1])
    assert sprung, "the bad run must spring at least one forbidden check"
