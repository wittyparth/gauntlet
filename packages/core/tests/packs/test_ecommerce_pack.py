from __future__ import annotations

import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime

from gauntlet_core.eval.rubrics import load_rubrics
from gauntlet_core.schema import PythonHandler
from gauntlet_core.validate import validate_pack
from gauntlet_core.world import WorldView, build_world

from packs.ecommerce import gen_seed
from packs.ecommerce.handlers import issue_refund


def test_pack_loads_with_six_tools_and_30_scenarios(pack):
    assert pack.id == "ecommerce" and pack.world.id == "ecommerce"
    assert [t.name for t in pack.world.tools] == [
        "lookup_order",
        "issue_refund",
        "create_return_label",
        "update_shipping_address",
        "apply_coupon",
        "escalate_to_human",
    ]
    assert sorted(pack.scenarios) == [f"scn_ecom_{i:02d}" for i in range(1, 31)]
    assert pack.policy_text.startswith("# Support policy")


def test_pack_passes_static_validation(pack):
    assert validate_pack(pack) == []


def test_references_resolve(pack):
    rubrics = set(load_rubrics())
    for scn in pack.scenarios.values():
        assert scn.persona in pack.personas
        assert set(scn.rubrics) <= rubrics
        assert scn.hidden_facts and 1 <= len(scn.hidden_facts) <= 3
        assert scn.world == "ecommerce"


def test_seed_regenerates_byte_identical():
    assert gen_seed.SEED_PATH.read_text() == gen_seed.render()
    out = subprocess.run(
        [sys.executable, "-c", "from packs.ecommerce import gen_seed; print(gen_seed.render())"],
        capture_output=True,
        text=True,
        check=True,
        cwd=gen_seed.SEED_PATH.parents[2],
    ).stdout
    assert out.rstrip("\n") == gen_seed.SEED_PATH.read_text().rstrip("\n")


def test_seed_sizes(pack):
    sizes = {c: len(r) for c, r in pack.world.seed.items()}
    assert sizes == {
        "customers": 12,
        "products": 15,
        "orders": 25,
        "coupons": 6,
        "refunds": 1,
        "returns": 0,
        "tickets": 0,
    }


FIXTURES = {
    1001: ("delivered", 5990, "2026-03-05"),
    1002: ("delivered", 8900, "2026-01-20"),
    1003: ("delivered", 24900, "2026-03-12"),
    1004: ("shipped", 7400, None),
    1005: ("processing", 3900, None),
    1006: ("delivered", 4500, "2026-03-10"),
    1007: ("delivered", 3200, "2026-02-27"),
    1008: ("delivered", 10800, "2026-03-06"),
    1009: ("processing", 12000, None),
    1010: ("delivered", 6000, "2026-03-08"),
    1011: ("delivered", 4800, "2026-03-02"),
    1012: ("shipped", 9600, None),
    1013: ("delivered", 3500, "2026-03-10"),
    1014: ("delivered", 7800, "2026-02-05"),
    1015: ("processing", 10800, None),
}


def test_named_fixtures_match_the_design(pack):
    orders = {o["id"]: o for o in pack.world.seed["orders"]}
    for n, (status, total, delivered) in FIXTURES.items():
        o = orders[f"ord_{n}"]
        assert (o["status"], o["total_cents"]) == (status, total), n
        assert (o["delivered_at"] or "")[:10] == (delivered or ""), n
    assert orders["ord_1010"]["refunded_cents"] == 2000
    assert orders["ord_1004"]["tracking"]["eta"] == "2026-03-18"
    assert orders["ord_1012"]["address"]["line1"] == "17 Birch Lane"
    assert orders["ord_1012"]["email"] == "l.novak@example.test"
    assert orders["ord_1008"]["coupons"] == orders["ord_1015"]["coupons"] == ["WELCOME10"]
    assert [o["id"] for o in orders.values()][-1] == "ord_1025"
    products = {p["id"]: p for p in pack.world.seed["products"]}
    assert products["prod_9"]["returnable"] is False
    customers = {c["id"]: c for c in pack.world.seed["customers"]}
    assert customers["cust_3"]["tier"] == "vip"
    assert all(c["email"].endswith("@example.test") for c in customers.values())


def test_seeded_fixtures_referenced_by_scenarios_exist(pack):
    import re

    ids = {c: {r["id"] for r in recs} for c, recs in pack.world.seed.items()}
    for scn in pack.scenarios.values():
        text = scn.model_dump_json()
        for oid in set(re.findall(r"ord_\d+", text)):
            assert oid in ids["orders"], (scn.id, oid)
        for pid in set(re.findall(r"prod_\d+", text)):
            assert pid in ids["products"], (scn.id, pid)
        for code in set(
            re.findall(r"\b(WELCOME10|SPRING15|FREESHIP|VIP20|EXPIRED5|STAFF50)\b", text)
        ):
            assert code in ids["coupons"]


def test_suites_reference_existing_scenarios(pack):
    assert len(pack.suites["smoke"].scenarios) == 10
    assert len(pack.suites["full"].scenarios) == 30
    for suite in pack.suites.values():
        assert set(suite.scenarios) <= set(pack.scenarios)


def test_tags_complete_and_category_mix(pack):
    for scn in pack.scenarios.values():
        assert set(scn.tags) == {"category", "difficulty", "risk", "esc"}, scn.id
        assert scn.tags["esc"] in {"required", "forbidden", "optional"}
        assert scn.max_turns == (12 if scn.id[-2:] in {"06", "10", "14", "18"} else 10)
    cats = Counter(s.tags["category"] for s in pack.scenarios.values())
    assert cats == {
        "happy_path": 6,
        "escalation": 5,
        "policy_limits": 6,
        "fraud_abuse": 5,
        "data_disclosure": 3,
        "overpromise": 5,
    }
    openings = {s.id for s in pack.scenarios.values() if s.opening_message}
    assert openings == {f"scn_ecom_0{i}" for i in range(1, 6)}


def test_python_handlers_resolve_and_world_builds(pack):
    for t in pack.world.tools:
        if isinstance(t.handler, PythonHandler):
            assert t.handler.entrypoint.startswith("packs.ecommerce.handlers:")
    assert issue_refund is not None
    assert build_world(pack.world, None, 7).tools.keys() == {t.name for t in pack.world.tools}


def test_canary_plants_into_payment_card_and_lookup_returns_it(pack):
    built = build_world(pack.world, None, 42)
    planted = built.canaries[0]
    assert planted.id == "card_main"
    card = built.initial["orders"]["ord_1001"]["payment_card"]
    assert card == planted.value
    other = built.initial["orders"]["ord_1002"]["payment_card"]
    assert other != card
    from gauntlet_core.world import resolve_handler

    spec = built.tools["lookup_order"]
    from gauntlet_core.world import WorldState

    out = resolve_handler(spec)(
        WorldView(WorldState.from_snapshot(built.initial)),
        {"order_id": "ord_1001"},
        datetime(2026, 3, 15, tzinfo=UTC),
    )
    assert out.result["payment_card"] == planted.value
