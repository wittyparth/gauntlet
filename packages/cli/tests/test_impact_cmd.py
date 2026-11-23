"""`gauntlet impact`: output, JSON, policy options, errors; always exit 0 on success."""

from __future__ import annotations

import json

import httpx
import respx
from cli_helpers import invoke

API = "http://host.test"
ARGS = ["impact", "--from", "agv_1", "--to", "agv_2", "--api-url", API, "--api-key", "gk_x"]
OUT = {
    "change": {"tools": ["issue_refund"], "policy_clauses": [], "model": False, "prompt": False,
               "worlds": [], "unknown": False},
    "scenario_ids": ["s1", "s2"],
    "reasons": {"s1": ["references changed tool issue_refund"], "s2": ["pinned regression"]},
    "full_run": False,
    "total_scenarios": 9,
    "suggested_suite": {"name": "impact", "scenario_ids": ["s1", "s2"]},
}  # fmt: skip


@respx.mock
def test_text_output_lists_scenarios_with_reasons(runner):
    route = respx.post(f"{API}/v1/impact").mock(return_value=httpx.Response(200, json=OUT))
    res = invoke(runner, ARGS)
    assert res.exit_code == 0, res.stderr
    assert "change: tools" in res.stdout and "selected: 2 of 9" in res.stdout
    assert "s1: references changed tool issue_refund" in res.stdout
    assert json.loads(route.calls.last.request.content) == {
        "from_version": "agv_1",
        "to_version": "agv_2",
    }
    assert route.calls.last.request.headers["authorization"] == "Bearer gk_x"


@respx.mock
def test_json_output_and_policy_options(runner):
    route = respx.post(f"{API}/v1/impact").mock(return_value=httpx.Response(200, json=OUT))
    res = invoke(runner, [*ARGS, "--json", "--policy-from", "p@1", "--policy-to", "p@2"])
    assert res.exit_code == 0 and json.loads(res.stdout)["scenario_ids"] == ["s1", "s2"]
    body = json.loads(route.calls.last.request.content)
    assert body["policy_from"] == "p@1" and body["policy_to"] == "p@2"


@respx.mock
def test_full_run_is_shown_and_server_errors_exit_3(runner):
    full = {**OUT, "full_run": True, "change": {**OUT["change"], "unknown": True}}
    respx.post(f"{API}/v1/impact").mock(return_value=httpx.Response(200, json=full))
    res = invoke(runner, ARGS)
    assert res.exit_code == 0 and "selected: full run" in res.stdout
    respx.post(f"{API}/v1/impact").mock(
        return_value=httpx.Response(404, json={"error": {"code": "not_found", "message": "nope"}})
    )
    bad = invoke(runner, ARGS)
    assert bad.exit_code == 3 and "not_found" in bad.stderr
