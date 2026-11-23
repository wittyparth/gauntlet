from gauntlet_core.impact import (
    Change,
    ImpactHistory,
    ScenarioInfo,
    classify_change,
    compute_impact,
)

S = ScenarioInfo
HIST = ImpactHistory(
    scenarios=(
        S("s_refund", tools=frozenset({"refund"}), risk="high"),
        S("s_lookup", tools=frozenset({"lookup"}), risk="low"),
        S("s_lookup2", tools=frozenset({"lookup"}), risk="low"),
        S("s_pinned", tools=frozenset(), pinned=True, risk="medium"),
        S("s_clause", tags={"clause": "refund-limit"}, risk="medium"),
        S("s_world", world_id="wld_a", risk="medium"),
        S("s_flip", risk="low"),
    ),
    flipped_recent=frozenset({"s_flip"}),
)


def test_tool_change_selects_referencing_plus_pinned_only():
    out = compute_impact(Change(tools=frozenset({"refund"})), HIST)
    assert out.scenario_ids == ["s_pinned", "s_refund"] and not out.full_run
    assert out.reasons["s_refund"] == ["references changed tool refund"]
    assert out.reasons["s_pinned"] == ["pinned regression"]


def test_policy_change_selects_tagged_clause():
    out = compute_impact(Change(policy_clauses=frozenset({"refund-limit"})), HIST)
    assert out.scenario_ids == ["s_clause", "s_pinned"]


def test_world_change():
    out = compute_impact(Change(worlds=frozenset({"wld_a"})), HIST)
    assert out.scenario_ids == ["s_pinned", "s_world"]


def test_model_change_selects_stratified_sample_flipped_and_pinned():
    out = compute_impact(Change(model=True), HIST)
    ids = set(out.scenario_ids)
    assert {"s_pinned", "s_flip", "s_refund"} <= ids  # pinned, flipped, the only high-risk one
    assert len(ids & {"s_lookup", "s_lookup2"}) <= 1  # low stratum: 25% of 3 rounds up to 1
    assert not out.full_run
    assert all(out.reasons[i] for i in out.scenario_ids)
    assert compute_impact(Change(model=True), HIST) == out  # deterministic


def test_unknown_change_sets_full_run():
    out = compute_impact(Change(unknown=True), HIST)
    assert out.full_run and len(out.scenario_ids) == len(HIST.scenarios)
    assert all(out.reasons[i] for i in out.scenario_ids)


def test_no_change_selects_nothing():
    out = compute_impact(Change(), HIST)
    assert out.scenario_ids == [] and not out.full_run


def test_classify_change():
    old = {"kind": "hosted", "model": "m1", "system_prompt": "p", "tools": ["a", "b"]}
    assert classify_change(old, dict(old)).empty
    c = classify_change(old, {**old, "tools": ["a", "c"]})
    assert c.tools == {"b", "c"} and not c.model and not c.unknown
    assert classify_change(old, {**old, "model": "m2"}).model
    assert classify_change(old, {**old, "system_prompt": "q"}).prompt
    assert classify_change(old, {**old, "endpoint": "http://x"}).unknown
    schema_old = {"tools": [{"name": "a", "schema": {"x": 1}}]}
    schema_new = {"tools": [{"name": "a", "schema": {"x": 2}}]}
    assert classify_change(schema_old, schema_new).tools == {"a"}
