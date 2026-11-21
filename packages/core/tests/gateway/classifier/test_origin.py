from gauntlet_core.gateway import Guard
from gauntlet_core.gateway.classifier import DEFAULT_ORIGIN_RULES, OriginRules
from gauntlet_core.schema import Policy

P = Policy(id="p", rules=[])


def test_glob_first_match_wins():
    rules = OriginRules(
        [
            {"tool": "crm_*", "trust": "system"},
            {"tool": "*", "trust": "untrusted_external"},
            {"tool": "crm_secret", "trust": "user"},
        ]
    )
    assert rules.match("crm_lookup") == "system"
    assert rules.match("crm_secret") == "system"  # the first match, not the most specific
    assert rules.match("anything") == "untrusted_external"


def test_default_untrusted_globs():
    r = OriginRules()
    for tool in ("web_fetch", "browse_page", "search_docs", "read_email", "inbox_list",
                 "scrape_site", "download_file", "files__fetch_url"):  # fmt: skip
        assert r.match(tool) == "untrusted_external", tool
    assert r.match("issue_refund") is None and len(DEFAULT_ORIGIN_RULES) == 8


def test_guard_precedence_rules_then_wrap_flag_then_defaults():
    g = Guard(P, origin_rules=[{"tool": "web_trusted", "trust": "system"}])
    assert g.origin_trust("web_trusted") == "system"  # configured beats the default `*web*`
    assert g.origin_trust("web_fetch") == "untrusted_external"  # default
    assert g.origin_trust("lookup") == "system"
    g.wrap(lambda: None, tool="custom_tool", untrusted_output=True)
    assert g.origin_trust("custom_tool") == "untrusted_external"
    g2 = Guard(P, origin_rules=[{"tool": "custom_tool", "trust": "system"}])
    g2.wrap(lambda: None, tool="custom_tool", untrusted_output=True)
    assert g2.origin_trust("custom_tool") == "system"  # an explicit rule overrides the flag
    assert Guard(P, use_origin_defaults=False).origin_trust("web_fetch") == "system"


async def test_session_uses_origin_rules_unless_told_otherwise():
    g = Guard(P)
    s = g.session()
    await s.record_tool_result("c1", "web_fetch", "x")
    await s.record_tool_result("c2", "web_fetch", "x", untrusted=False)
    await s.record_tool_result("c3", "lookup", "x")
    await s.record_tool_result("c4", "lookup", "x", untrusted=True, source="crm")
    trust = [e.origin.trust for e in s.events if e.origin]
    assert trust == ["untrusted_external", "system", "system", "untrusted_external"]


async def test_mcp_trust_propagates():
    from gauntlet_core.gateway.mcp import McpGatewayConfig

    cfg = McpGatewayConfig.model_validate(
        {"servers": [{"name": "a", "transport": "http", "url": "http://a"},
                     {"name": "b", "transport": "http", "url": "http://b", "trust": "trusted"}]}
    )  # fmt: skip
    assert [cfg.server(n).trust for n in "ab"] == ["untrusted", "trusted"]
    # the proxy passes `untrusted=<server trust>` explicitly, which beats every glob
    g = Guard(P)
    s = g.session()
    await s.record_tool_result(
        "c", "b__web_fetch", "x", untrusted=cfg.server("b").trust == "untrusted"
    )
    assert s.events[-1].origin is not None and s.events[-1].origin.trust == "system"
