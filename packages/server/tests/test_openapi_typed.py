"""Every `/v1` route declares a typed response (the web client is generated from it)."""

from __future__ import annotations

from gauntlet_server.app import create_app

# no body, a stream, or intentionally unimplemented
UNTYPED = {
    ("get", "/v1/runs/{run_id}/stream"),
    ("get", "/v1/runs/{run_id}/compare"),
    ("post", "/v1/episodes/{episode_id}/rejudge"),
    ("post", "/v1/agents/{agent_id}/generate-scenarios"),
    ("post", "/v1/worlds/import-openapi"),
}


def test_every_v1_route_has_a_typed_json_response():
    schema = create_app().openapi()
    untyped = []
    for path, ops in schema["paths"].items():
        if not path.startswith("/v1"):
            continue
        for method, op in ops.items():
            if (method, path) in UNTYPED:
                continue
            ok = [c for c in op["responses"] if c.startswith("2")]
            assert ok, (method, path)
            if ok[0] == "204":
                continue
            body = op["responses"][ok[0]].get("content", {}).get("application/json", {})
            node = body.get("schema", {})
            typed = "$ref" in node or "anyOf" in node or node.get("type") == "array"
            if not typed:
                untyped.append(f"{method.upper()} {path}")
    assert not untyped, untyped
