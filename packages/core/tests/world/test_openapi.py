from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from gauntlet_core.schema import CrudHandler, LLMSimHandler, WorldSpec
from gauntlet_core.world import WorldState, WorldView, resolve_handler, validate_args
from gauntlet_core.world.openapi import import_openapi
from hypothesis import given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator

FIX = Path(__file__).parents[1] / "fixtures" / "openapi"
NOW = datetime(2026, 3, 15, tzinfo=UTC)


def tools(imp):
    return {t.name: t for t in imp.tools}


def test_petstore_three_collections_and_crud_ops_inferred():
    imp = import_openapi(FIX / "petstore.json")
    assert set(imp.seed) == {"pets", "owners", "stores"}
    t = tools(imp)
    assert set(t) == {
        "list_pets",
        "create_pet",
        "get_pet",
        "update_pet",
        "delete_pet",
        "list_owners",
        "get_owner",
        "list_stores",
    }
    h = {n: s.handler for n, s in t.items()}
    assert h["list_pets"] == CrudHandler(collection="pets", op="list", filter_args=["status"])
    assert h["create_pet"] == CrudHandler(collection="pets", op="create")
    assert h["get_pet"] == CrudHandler(collection="pets", op="get", key_arg="petId")
    assert h["update_pet"] == CrudHandler(collection="pets", op="update", key_arg="petId")
    assert h["delete_pet"] == CrudHandler(collection="pets", op="delete", key_arg="petId")
    assert h["get_owner"] == CrudHandler(collection="owners", op="get", key_arg="ownerId")
    # the integer id parameter is a string so it matches the seeded ids
    assert t["get_pet"].input_schema["properties"]["petId"]["type"] == "string"
    assert t["create_pet"].input_schema["required"] == ["name"]
    assert t["list_pets"].input_schema["properties"]["limit"] == {"type": "integer"}


def test_nested_path_becomes_llm_sim_with_a_warning():
    imp = import_openapi(FIX / "nested.yaml")
    t = tools(imp)
    sim = t["list_user_orders"].handler
    assert isinstance(sim, LLMSimHandler)
    assert sim.instructions.startswith("Orders of one user")
    assert isinstance(t["post_users_user_id_orders_order_id_cancel"].handler, LLMSimHandler)
    assert isinstance(t["upload_file"].handler, LLMSimHandler)  # multipart body
    assert any("GET /users/{userId}/orders" in w and "LLM" in w for w in imp.warnings)
    assert any("non-JSON body" in w for w in imp.warnings)


def test_llm_sim_instructions_truncated_to_500():
    doc = {
        "openapi": "3.0.0",
        "paths": {"/a/{id}/b": {"post": {"summary": "s", "description": "x" * 900}}},
    }
    sim = import_openapi(doc).tools[0].handler
    assert isinstance(sim, LLMSimHandler) and len(sim.instructions) == 500


def test_risk_table():
    t = tools(import_openapi(FIX / "shop.yaml"))
    assert t["refund_order"].risk == "financial"
    assert t["delete_order"].risk == "destructive"
    assert t["send_receipt"].risk == "external_comm"
    assert t["create_order"].risk == "write"
    assert t["update_order"].risk == "write"
    assert t["get_order"].risk == "read"


def test_names_unique_valid_and_collisions_suffixed():
    imp = import_openapi(FIX / "shop.yaml")
    names = [t.name for t in imp.tools]
    assert len(set(names)) == len(names)
    assert all(re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", n) for n in names)
    doc = {
        "openapi": "3.0.0",
        "paths": {
            "/a": {"get": {"operationId": "dupOp"}, "post": {"operationId": "dupOp"}},
            "/b": {"get": {"operationId": "dupOp"}},
        },
    }
    assert [t.name for t in import_openapi(doc).tools] == ["dup_op", "dup_op_2", "dup_op_3"]


def test_fallback_name_from_method_and_path():
    doc = {"openapi": "3.0.0", "paths": {"/things/{thingId}": {"get": {}}}}
    assert import_openapi(doc).tools[0].name == "get_things_thing_id"


def test_refs_resolved_and_external_ref_warns():
    imp = import_openapi(FIX / "nested.yaml")
    assert any("external $ref" in w for w in imp.warnings)
    assert tools(imp)["list_links"].handler == CrudHandler(collection="links", op="list")
    assert all(set(r) == {"id"} for r in imp.seed["links"])  # property became {}
    shop = import_openapi(FIX / "shop.yaml")
    assert {"id", "name", "price_cents", "in_stock"} <= set(shop.seed["products"][0])


def test_recursive_ref_stops_at_depth_limit_and_seed_is_finite():
    imp = import_openapi(FIX / "nested.yaml")
    assert any("exceeds depth" in w for w in imp.warnings)
    node = imp.seed["nodes"][0]
    assert node["id"] == "node_1" and isinstance(node["child"], dict)


def test_seed_deterministic_and_sizes_match():
    a = import_openapi(FIX / "shop.yaml", seed_per_collection=5, rng_seed=3)
    b = import_openapi(FIX / "shop.yaml", seed_per_collection=5, rng_seed=3)
    c = import_openapi(FIX / "shop.yaml", seed_per_collection=5, rng_seed=4)
    assert a.seed == b.seed != c.seed
    assert {k: len(v) for k, v in a.seed.items()} == {"products": 5, "orders": 5, "customers": 5}
    assert [r["id"] for r in a.seed["orders"]] == [f"order_{n}" for n in range(1, 6)]
    order = a.seed["orders"][1]
    assert order["status"] == "paid"  # enum cycled
    assert 500 <= order["total_cents"] <= 50000
    assert order["created"].startswith("2026-")
    cust = a.seed["customers"][0]
    assert cust["email"] == "user1@example.test"
    assert re.fullmatch(r"[0-9a-f-]{36}", cust["token"])


def test_untrusted_extension_honoured_and_heuristic_warns():
    imp = import_openapi(FIX / "nested.yaml")
    t = tools(imp)
    assert t["list_nodes"].untrusted_output and not any("list_nodes" in w for w in imp.warnings)
    assert t["list_comments"].untrusted_output
    assert any("list_comments: marked untrusted by heuristic" in w for w in imp.warnings)
    assert not tools(import_openapi(FIX / "shop.yaml"))["get_order"].untrusted_output


def test_swagger_2_rejected():
    with pytest.raises(ValueError, match=r"Swagger 2\.0"):
        import_openapi({"swagger": "2.0", "paths": {"/a": {}}})
    with pytest.raises(ValueError, match="not an OpenAPI 3"):
        import_openapi({"paths": {"/a": {}}})


def test_accepts_dict_json_text_yaml_text_and_path():
    text = (FIX / "petstore.json").read_text()
    a = import_openapi(json.loads(text))
    b = import_openapi(text)
    c = import_openapi(str(FIX / "petstore.json"))
    d = import_openapi(FIX / "petstore.json")
    assert a.tools == b.tools == c.tools == d.tools
    assert (
        import_openapi((FIX / "shop.yaml").read_text()).tools
        == import_openapi(FIX / "shop.yaml").tools
    )


def test_max_tools():
    imp = import_openapi(FIX / "shop.yaml", max_tools=3)
    assert len(imp.tools) == 3
    assert sum("max_tools" in w for w in imp.warnings) == 1


def test_pagination_params_are_not_filters():
    doc = {
        "openapi": "3.0.0",
        "paths": {
            "/things": {
                "get": {
                    "parameters": [
                        {"name": "limit", "in": "query", "schema": {"type": "integer"}},
                        {"name": "color", "in": "query", "schema": {"type": "string"}},
                    ]
                }
            }
        },
    }
    h = import_openapi(doc).tools[0].handler
    assert isinstance(h, CrudHandler) and h.filter_args == ["color"]


def test_round_trip_tools_run_against_generated_seed():
    imp = import_openapi(FIX / "shop.yaml", seed_per_collection=4)
    world = imp.to_world("shop", datetime(2026, 3, 15, tzinfo=UTC))
    assert WorldSpec.model_validate(world.model_dump(mode="json")) == world
    state = WorldState.from_seed(world.seed)
    t = tools(imp)

    def call(name: str, args: dict):
        assert validate_args(t[name].input_schema, args) is None
        out = resolve_handler(t[name])(WorldView(state), args, NOW)
        state.apply(out.patch)
        return out

    assert len(call("list_orders", {}).result) == 4
    shipped = call("list_orders", {"status": "shipped"}).result
    assert shipped and all(o["status"] == "shipped" for o in shipped)
    assert call("get_order", {"orderId": "order_2"}).result["id"] == "order_2"
    assert call("get_order", {"orderId": "nope"}).error == "not_found"
    created = call("create_order", {"customer_id": "customer_1", "total_cents": 900}).result
    assert created["id"] == "order_5" and state.get("orders", "order_5")
    call("update_order", {"orderId": "order_5", "status": "paid"})
    created_order = state.get("orders", "order_5")
    assert created_order is not None and created_order["status"] == "paid"
    call("delete_order", {"orderId": "order_5"})
    assert state.get("orders", "order_5") is None
    assert call("get_customer", {"customerId": "customer_1"}).result["name"]
    assert call("list_products", {}).result[0]["id"] == "product_1"
    assert validate_args(t["create_order"].input_schema, {}) is not None  # customer_id required


_NAME = st.text(alphabet="abcdefgxyz", min_size=1, max_size=6)


@st.composite
def small_specs(draw):
    paths: dict = {}
    for _ in range(draw(st.integers(1, 5))):
        segs = [draw(_NAME) for _ in range(draw(st.integers(1, 3)))]
        if draw(st.booleans()):
            segs.append("{" + draw(_NAME) + "}")
        path = "/" + "/".join(segs)
        ops: dict = {}
        for method in draw(
            st.lists(st.sampled_from(["get", "post", "put", "patch", "delete"]), max_size=3)
        ):
            op: dict = {}
            if draw(st.booleans()):
                op["operationId"] = draw(st.text(min_size=0, max_size=80))
            params = [
                {
                    "name": draw(_NAME),
                    "in": "query",
                    "schema": {"type": draw(st.sampled_from(["string", "integer", "boolean"]))},
                }
                for _ in range(draw(st.integers(0, 2)))
            ]
            for seg in segs:
                if seg.startswith("{"):
                    params.append(
                        {
                            "name": seg[1:-1],
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    )
            if params:
                op["parameters"] = params
            if method in ("post", "put", "patch") and draw(st.booleans()):
                op["requestBody"] = {
                    "content": {
                        "application/json": {
                            "schema": {"type": "object", "properties": {"f": {"type": "string"}}}
                        }
                    }
                }
            ops[method] = op
        if ops:
            paths[path] = ops
    if not paths:
        paths["/x"] = {"get": {}}
    return {"openapi": "3.0.0", "paths": paths}


@settings(max_examples=60, deadline=None)
@given(small_specs())
def test_property_names_valid_and_schemas_are_json_schema(spec):
    imp = import_openapi(spec)
    names = [t.name for t in imp.tools]
    assert len(set(names)) == len(names)
    for t in imp.tools:
        assert re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", t.name), t.name
        Draft202012Validator.check_schema(t.input_schema)
