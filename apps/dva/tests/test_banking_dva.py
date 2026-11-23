"""Banking DVA: the suite runs through the CLI against the scripted DVA, and each flaw springs
its scenarios. No model."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
import uvicorn
import yaml
from dva.app import create_app
from dva.banking_agent.agent import respond
from dva.config import Settings, world_file
from dva.flaws import FLAWS
from dva_helpers import free_port, serving
from gauntlet_cli.main import app as cli
from gauntlet_core.eval import RunReport
from gauntlet_core.packs import load_pack
from gauntlet_core.schema import WorldSpec, load_yaml
from pack_runner import inline, run_scenario_checks
from typer.testing import CliRunner

REPO = Path(__file__).parents[3]
ALL = {f.id for f in FLAWS.values() if f.agent == "banking"}
FAKE = Path(__file__).parent / "fixtures" / "fake_llm_banking_smoke.yaml"


@pytest.fixture(scope="module")
def pack():
    return load_pack(REPO / "packs" / "banking")


def sid(n: int) -> str:
    return f"scn_bank_{n:02d}"


async def sprung(pack, fixed: bool, flaws: set[str]) -> dict[str, list[str]]:
    world = load_yaml(WorldSpec, world_file("banking", "fixed" if fixed else "unfixed"))
    out = {}
    async with serving(flaws, respond) as (dva, facade):
        for scn in pack.scenarios.values():
            out[scn.id] = await run_scenario_checks(world, inline(scn, world), dva, facade)
    return out


async def test_no_flaws_springs_nothing(pack):
    assert not any((await sprung(pack, False, set())).values())
    assert not any((await sprung(pack, True, set())).values())


def test_fixed_world_handlers_enforce_the_session(pack):
    """The scoped handlers refuse other accounts (F51/F58), unverified sessions (F50) and
    payees right after a credential reset (F52); the pack's handlers do none of that."""
    from datetime import UTC, datetime

    from dva.banking_agent import flaws as fx
    from gauntlet_core.world import WorldState, WorldView, assert_pure

    now = datetime(2026, 3, 15, tzinfo=UTC)

    def call(fn, session, **args):
        sess = {"id": "current", "customer_id": "cust_1", "verified": True,
                "credential_reset_hours_ago": 500, **session}  # fmt: skip
        view = WorldView(WorldState.from_seed(pack.world.seed | {"session": [sess]}))
        assert_pure(fn, view, dict(args), now)
        return fn(view, dict(args), now)

    assert call(fx.get_balance_scoped, {}, account_id="acct_1001").result["id"] == "acct_1001"
    assert call(fx.get_balance_scoped, {}, account_id="acct_2001").error == "not_found"
    assert call(fx.get_balance_scoped, {"verified": False}, account_id="acct_1001").error == (
        "not_verified"
    )
    assert call(fx.list_transactions_scoped, {}, account_id="acct_2001").error == "not_found"
    assert call(fx.file_dispute_guarded, {}, transaction_id="txn_201", reason="x").error == (
        "not_found"
    )
    pay = {"account_id": "acct_1001", "name": "N", "account_ref": "1"}
    assert call(fx.add_payee_guarded, {"credential_reset_hours_ago": 3}, **pay).error == (
        "recent_credential_reset"
    )
    assert call(fx.add_payee_guarded, {}, **pay).result["payee_id"] == "pay_2"


def test_dva_banking_worlds_differ_only_in_handlers(pack):
    unsafe = load_yaml(WorldSpec, world_file("banking", "unfixed"))
    fixed = load_yaml(WorldSpec, world_file("banking", "fixed"))
    assert unsafe.seed == fixed.seed == pack.world.seed
    assert [t.handler for t in unsafe.tools] == [t.handler for t in pack.world.tools]
    changed = {
        a.name for a, b in zip(fixed.tools, unsafe.tools, strict=True) if a.handler != b.handler
    }
    assert changed == {"get_balance", "list_transactions", "file_dispute", "add_payee"}


@pytest.mark.parametrize(
    ("flaws", "expected"),
    [
        ({"F50"}, set()),
        ({"F51"}, {9, 12}),
        ({"F52"}, {5}),
        ({"F53"}, {4, 7}),
        ({"F54"}, {6}),
        ({"F55"}, {8}),
        ({"F56"}, {20}),
        ({"F57"}, {11}),
    ],
)
async def test_each_flaw_springs_its_scenarios(pack, flaws, expected):
    result = await sprung(pack, False, flaws)
    assert {n for n in range(1, 21) if result[sid(n)]} == expected


def serve(flaws: set[str]) -> tuple[uvicorn.Server, str]:
    port = free_port()
    dva = create_app(
        lambda: flaws, Settings(brain="scripted", mock_base="http://127.0.0.1:1"), scripted=respond
    )
    server = uvicorn.Server(uvicorn.Config(dva, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.02)
    return server, f"http://127.0.0.1:{port}"


def run_cli(tmp_path: Path, flaws: set[str]) -> dict[str, int]:
    tmp_path.mkdir(parents=True)
    server, url = serve(flaws)
    try:
        agent = tmp_path / "agent.yaml"
        agent.write_text(
            yaml.safe_dump(
                {
                    "label": "dva-banking",
                    "target": {
                        "kind": "openai_compat",
                        "base_url": f"{url}/v1",
                        "model": "dva",
                        "wired": True,
                    },
                }
            )
        )
        args = ["run", str(REPO / "packs" / "banking"), "--target", str(agent), "--suite", "smoke"]
        args += ["--fake-llm", str(FAKE), "--no-judge", "--json", "--out", str(tmp_path / "run")]
        res = CliRunner().invoke(cli, args)
    finally:
        server.should_exit = True
    assert res.exit_code == 0, res.stderr
    report = RunReport.model_validate_json(res.stdout)
    assert report.counted == 6 and report.excluded == {}
    return {s.scenario_id: s.passed for s in report.per_scenario}


def test_banking_smoke_suite_through_the_cli(tmp_path):
    assert all(run_cli(tmp_path / "ok", set()).values())
    bad = run_cli(tmp_path / "bad", {"F51", "F53"})
    assert {k for k, v in bad.items() if not v} == {sid(4), sid(9)}
