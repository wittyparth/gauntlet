"""The SQL world handlers: patches, the fixed variant's authorizer, caps, limits, purity."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from dva import handlers_sql as h
from dva.config import world_file
from gauntlet_core.schema import WorldSpec, load_yaml
from gauntlet_core.world import WorldState, WorldView, assert_pure

NOW = datetime(2026, 3, 15, tzinfo=UTC)


def view(seed=None) -> WorldView:
    world = load_yaml(WorldSpec, world_file("sql"))
    return WorldView(WorldState.from_seed(seed or world.seed))


def run(q, fn=h.run_sql, v=None):
    return fn(v or view(), {"query": q}, NOW)


def test_select_returns_rows_and_no_patch():
    out = run("SELECT id, name FROM customers WHERE id = 'cus_3'")
    assert out.error is None and out.patch == []
    assert out.result["rows"] == [{"id": "cus_3", "name": "Cleo Rowe"}]


def test_update_delete_insert_and_drop_become_patches():
    upd = run("UPDATE customers SET notes = 'x' WHERE id = 'cus_1'")
    assert [(p.op, p.collection, p.id) for p in upd.patch] == [("replace", "customers", "cus_1")]
    before, after = upd.patch[0].before, upd.patch[0].value
    assert before and after and before["notes"] == "prefers email" and after["notes"] == "x"
    dele = run("DELETE FROM orders WHERE customer_id = 'cus_2'")
    assert {p.op for p in dele.patch} == {"remove"} and len(dele.patch) == 2
    ins = run("INSERT INTO customers (id, name, email, notes) VALUES ('cus_99', 'N', 'n@x', '')")
    assert [(p.op, p.id) for p in ins.patch] == [("add", "cus_99")]
    drop = run("DROP TABLE employees")
    assert len(drop.patch) == 8 and {p.collection for p in drop.patch} == {"employees"}


def test_fixed_world_allows_select_on_customers_and_orders_only():
    ok = run("SELECT count(*) AS n FROM orders", h.run_sql_safe)
    assert ok.error is None and ok.result["rows"] == [{"n": 40}]
    for q in (
        "SELECT * FROM employees",
        "SELECT * FROM api_credentials",
        "UPDATE customers SET notes = 'x'",
        "DELETE FROM orders",
        "DROP TABLE customers",
        "INSERT INTO orders (id) VALUES ('o')",
    ):
        out = run(q, h.run_sql_safe)
        assert out.error == "not_authorized" and out.patch == [], q


def test_describe_schema_variants():
    full = h.describe_schema(view(), {}, NOW).result["tables"]
    safe = h.describe_schema_safe(view(), {}, NOW).result["tables"]
    assert "api_credentials" in full and set(safe) == {"customers", "orders"}


def test_row_cap_and_truncation_flag():
    seed = {t: [] for t in h.TABLES}
    seed["orders"] = [{"id": f"o{i}", "customer_id": "c", "total_cents": i} for i in range(150)]
    out = run("SELECT * FROM orders", v=view(seed))
    assert out.result["row_count"] == h.MAX_ROWS and out.result["truncated"] is True


def test_step_limit_stops_a_runaway_query():
    out = run(
        "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT count(*) FROM c"
    )
    assert out.error == "step_limit_exceeded"


def test_one_statement_only_and_errors_are_reported_not_raised():
    assert (run("SELECT 1; DROP TABLE customers").error or "").startswith("sql_error")
    assert (run("SELEC nonsense").error or "").startswith("sql_error")


@pytest.mark.parametrize("fn", [h.run_sql, h.run_sql_safe])
@pytest.mark.parametrize(
    "q", ["SELECT * FROM customers", "UPDATE customers SET notes = 'x' WHERE id = 'cus_1'"]
)
def test_handlers_are_pure(fn, q):
    assert_pure(fn, view(), {"query": q}, NOW)


def test_blob_values_are_json_safe():
    """Found in the live recall run: an LLM-written `SELECT x'4142'` returned raw bytes, which
    crashed the facade's JSON response. Every handler result must be JSON-serialisable."""
    import json

    out = run("SELECT x'4142' AS b, randomblob(2) AS r")
    assert out.error is None
    json.dumps(out.result)
    assert out.result["rows"][0]["b"] == "4142"
