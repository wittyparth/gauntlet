"""tau-bench retail importer on a miniature upstream-format checkout."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import yaml
from gauntlet_core.packs import load_pack
from gauntlet_core.validate import validate_pack
from gauntlet_core.world import WorldState, WorldView, assert_pure
from helpers import FIXTURES, holds, run_calls

from tools.import_benchmarks import tau_handlers as h
from tools.import_benchmarks.common import PinError
from tools.import_benchmarks.tau_bench import PIN, import_tau_bench, read_tasks

SRC = FIXTURES / "tau_mini"
NOW = datetime(2026, 3, 15, tzinfo=UTC)


@pytest.fixture(scope="module")
def imported(tmp_path_factory):
    out = tmp_path_factory.mktemp("tau") / "taubench_retail"
    report = import_tau_bench(SRC, out, pin=PIN)
    return out, report


def test_report_counts_reasons_and_portable_percentage(imported):
    _, report = imported
    assert (report.tasks, report.portable) == (7, 4) and report.portable_pct == 57.1
    assert {s.item: s.reason.split(":")[0] for s in report.skipped} == {
        "tau_retail_004": "unported_tool",
        "tau_retail_005": "replay_error",
        "tau_retail_006": "no_checkable_outcome",
    }
    assert "4/7 portable (57.1%)" in report.summary()


def test_pack_loads_validates_and_records_the_import(imported):
    out, _ = imported
    pack = load_pack(out)
    assert validate_pack(pack) == []
    assert sorted(pack.scenarios) == [f"tau_retail_00{i}" for i in range(4)]
    meta = yaml.safe_load((out / "pack.yaml").read_text())["import"]
    assert meta["pin"] == PIN and meta["licence"] == "MIT" and meta["portable_pct"] == 57.1
    assert pack.policy_text.startswith("# Retail agent policy")
    skipped = yaml.safe_load((out / "skipped.yaml").read_text())
    assert len(skipped) == 3 and all(s["reason"] for s in skipped)


def test_tool_names_and_descriptions_come_from_upstream(imported):
    pack = load_pack(imported[0])
    tools = {t.name: t for t in pack.world.tools}
    assert tools["cancel_pending_order"].description.startswith("Cancel a pending order")
    assert "exchange_delivered_order_items" not in tools  # not ported
    assert tools["get_order_details"].input_schema["required"] == ["order_id"]


def test_refuses_without_the_recorded_pin(tmp_path, capsys):
    with pytest.raises(PinError, match="recorded upstream pin"):
        import_tau_bench(SRC, tmp_path / "x", pin="main")
    assert not (tmp_path / "x").exists()
    import_tau_bench(SRC, tmp_path / "y", pin="main", allow_unpinned=True)
    assert "WARNING" in capsys.readouterr().err


def run(pack, fn, **args):
    view = WorldView(WorldState.from_seed(pack.world.seed))
    assert_pure(fn, view, dict(args), NOW)
    return fn(view, dict(args), NOW)


def test_handlers_are_pure_and_match_the_upstream_golden_results(imported):
    pack = load_pack(imported[0])
    assert run(pack, h.find_user_id_by_email, email="MIA.GARCIA@example.com").result == (
        "mia_garcia_4516"
    )
    assert run(pack, h.find_user_id_by_name_zip, first_name="Noah", last_name="Lee", zip="73301")
    assert run(pack, h.get_order_details, order_id="#W9").error == "Error: order not found"
    assert run(pack, h.list_all_product_types).result == {"Desk Lamp": "P1", "Notebook": "P2"}
    cancel = run(pack, h.cancel_pending_order, order_id="#W1", reason="no longer needed")
    assert cancel.result["status"] == "cancelled"
    assert cancel.result["payment_history"][-1] == {
        "transaction_type": "refund",
        "amount": 40.0,
        "payment_method_id": "gift_card_1",
    }
    refunded = next(p.value for p in cancel.patch if p.collection == "users")
    assert refunded["payment_methods"]["gift_card_1"]["balance"] == 50.0
    assert run(pack, h.cancel_pending_order, order_id="#W3", reason="ordered by mistake").error == (
        "Error: non-pending order cannot be cancelled"
    )
    ret = run(
        pack,
        h.return_delivered_order_items,
        order_id="#W3",
        item_ids=["I21"],
        payment_method_id="credit_card_1",
    )
    assert ret.result["status"] == "return requested" and ret.result["return_items"] == ["I21"]
    bad = run(
        pack,
        h.return_delivered_order_items,
        order_id="#W3",
        item_ids=["I21"],
        payment_method_id="paypal_x",
    )
    assert bad.error == "Error: payment method not found"
    assert run(pack, h.transfer_to_human_agents, summary="x").result == "Transfer successful"


async def test_oracle_replaying_ground_truth_holds_and_a_perturbation_fails(imported):
    out, _ = imported
    pack = load_pack(out)
    tasks = read_tasks(SRC / "tau_bench" / "envs" / "retail" / "tasks_test.py")
    for i in range(4):
        scn = pack.scenarios[f"tau_retail_{i:03d}"]
        calls = [(a["name"], a["kwargs"]) for a in tasks[i]["actions"]]
        text = " ".join(tasks[i]["outputs"]) or "done"
        assert holds(scn.success, await run_calls(pack, scn, calls, text)), i
        bad = await run_calls(pack, scn, calls[:-1], "nothing useful")
        assert not holds(scn.success, bad), i
    scn = pack.scenarios["tau_retail_001"]
    kw = dict(tasks[1]["actions"][0]["kwargs"], city="Elsewhere")
    assert not holds(
        scn.success, await run_calls(pack, scn, [("modify_pending_order_address", kw)])
    )
