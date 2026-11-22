import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "checks"))

from check_helpers import Tb
from gauntlet_core.mining import world_from_trace
from gauntlet_core.packs import load_pack

ROOT = Path(__file__).resolve().parents[4]
WORLD = next(iter(load_pack(ROOT / "packs" / "ecommerce").worlds.values()))


def test_crud_results_seed_records_by_collection():
    tb = Tb()
    tb.call("lookup_order", {"order_id": "o1"}, result='{"id": "o1", "status": "shipped"}')
    tb.call("lookup_order", {"order_id": "o2"}, result='{"id": "o2", "status": "processing"}')
    tb.call("lookup_order", {"order_id": "o1"}, result='{"id": "o1", "status": "shipped"}')
    overrides, unmapped = world_from_trace(tb.events, WORLD)
    assert overrides == {
        "orders": [
            {"id": "o1", "status": "shipped"},
            {"id": "o2", "status": "processing"},
        ]
    }
    assert unmapped == []


def test_python_handlers_unknown_tools_and_bad_results_are_reported_not_invented():
    tb = Tb()
    tb.call("issue_refund", {"order_id": "o1"}, result='{"id": "r1"}')  # a python handler
    tb.call("mystery", {}, result="{}")
    tb.call("lookup_order", {"order_id": "o9"}, result="not json at all")
    tb.call("lookup_order", {"order_id": "o8"}, result='{"status": "no id"}')
    tb.call("lookup_order", {"order_id": "o7"}, ok=False, result=None)
    overrides, unmapped = world_from_trace(tb.events, WORLD)
    assert overrides == {}
    assert "issue_refund" in unmapped and "mystery" in unmapped
    assert any("not JSON" in u for u in unmapped) and any("without an id" in u for u in unmapped)
