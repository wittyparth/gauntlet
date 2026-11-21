import json
from pathlib import Path

from gauntlet_core.gateway.mcp import ScanHook
from gauntlet_core.security.scan import scan_mcp_tools

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "mcp"


def tools(name: str) -> list[dict]:
    return json.loads((FIX / f"{name}.json").read_text())["tools"]


def test_poisoned_tools_are_blocked_with_their_rule_ids():
    hook = ScanHook(block_at="high")
    blocked = hook.blocked(tools("poisoned"))
    assert blocked  # at least the injected tool
    assert "add_numbers" in blocked
    rules = {f.rule_id for f in blocked["add_numbers"]}
    assert "MCP-001" in rules
    assert all(f.severity in ("high", "critical") for fs in blocked.values() for f in fs)


def test_clean_tools_pass():
    assert ScanHook().blocked(tools("clean")) == {}


def test_block_at_threshold():
    ts = tools("poisoned")
    assert len(ScanHook(block_at="critical").blocked(ts)) <= len(
        ScanHook(block_at="low").blocked(ts)
    )
    assert ScanHook(block_at="low").blocked(ts)


def test_only_the_spec_rules_hide_tools():
    findings = ScanHook().findings(tools("poisoned"))
    assert findings and all(f.rule_id != "MCP-012" for f in findings)
    assert {f.rule_id for f in findings} <= {f"MCP-{n:03d}" for n in (1, 2, 3, 4, 5, 6, 7, 8, 11)}


def test_cache_hit_on_an_unchanged_listing_and_miss_on_a_changed_one():
    calls = []

    def counting(listing):
        calls.append(1)
        return scan_mcp_tools(listing)

    hook = ScanHook(scan_fn=counting)
    ts = tools("clean")
    hook.blocked(ts)
    hook.blocked(list(reversed(ts)))  # same tools, other order: still a hit
    assert len(calls) == 1 and hook.scans == 1
    changed = [{**ts[0], "description": "A different description."}, *ts[1:]]
    hook.blocked(changed)
    assert len(calls) == 2
    hook.blocked(ts)  # the original listing is still cached
    assert len(calls) == 2
