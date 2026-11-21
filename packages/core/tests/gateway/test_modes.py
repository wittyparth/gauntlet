import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pytest
from gauntlet_core.gateway import Guard, MemorySink
from gw_helpers import REFUND_CAP, policy, rule, tool


async def one(guard, tool_name="issue_refund", **args):
    d = await guard.session().check_tool_call(tool_name, args or {"amount_cents": 20000})
    return d


async def test_shadow_never_blocks_and_records_would_have():
    sink = MemorySink()
    g = Guard(policy(REFUND_CAP, mode="shadow"), sink=sink)
    d = await one(g)
    assert d.action == "allow" and d.rule_id == "refund-cap"  # reported, not enforced
    (rec,) = sink.records
    assert (rec.action, rec.enforced, rec.would_have) == ("allow", False, "block")
    assert (rec.rule_id, rec.severity, rec.mode) == ("refund-cap", "critical", "shadow")
    assert (rec.policy_id, rec.policy_version, rec.kind, rec.tool) == (
        "pol_t",
        3,
        "tool_call",
        "issue_refund",
    )
    assert rec.evidence and rec.overhead_us >= 0 and rec.guard_error is None


async def test_enforce_blocks():
    sink = MemorySink()
    g = Guard(policy(REFUND_CAP, mode="enforce"), sink=sink)
    d = await one(g)
    assert d.action == "block" and d.message == "Refunds over 10000 cents are not allowed."
    rec = sink.records[0]
    assert (rec.action, rec.enforced, rec.would_have) == ("block", True, None)


async def test_clean_call_has_no_would_have():
    sink = MemorySink()
    g = Guard(policy(REFUND_CAP, mode="shadow"), sink=sink)
    await one(g, "issue_refund", amount_cents=5)
    assert sink.records[0].would_have is None and sink.records[0].action == "allow"


@pytest.mark.parametrize(
    ("policy_mode", "override", "blocked"),
    [("shadow", None, False), ("enforce", None, True), ("shadow", "enforce", True),
     ("enforce", "shadow", False)],
)  # fmt: skip
async def test_mode_override(policy_mode, override, blocked):
    g = Guard(policy(REFUND_CAP, mode=policy_mode), mode=override)
    assert (await one(g)).action == ("block" if blocked else "allow")


async def test_shadow_does_not_modify_or_hold_and_still_grows_the_prefix():
    redact = rule("r", tool("send", args={"body": {"regex": r"\d{4}"}}), action="redact")
    approve = rule("a", tool("pay"), action="require_approval")
    sink = MemorySink()
    g = Guard(policy(redact, approve, mode="shadow"), sink=sink)  # no approval handler at all
    s = g.session()
    d = await s.check_tool_call("send", {"body": "pin 1234"})
    assert d.action == "allow" and d.modified is None
    d = await s.check_tool_call("pay", {"amount": 1})
    assert d.action == "allow"
    assert [e.kind for e in s.events] == ["tool_call", "tool_call"]
    assert s.events[0].payload["args"] == {"body": "pin 1234"}  # unmodified
    assert [r.would_have for r in sink.records] == ["redact", "require_approval"]


async def test_log_action_runs_and_records():
    sink = MemorySink()
    g = Guard(policy(rule("l", tool("x"), action="log")), sink=sink)
    d = await g.session().check_tool_call("x", {})
    assert d.action == "log"
    assert sink.records[0].action == "log" and sink.records[0].enforced


async def test_reload_swaps_policy_atomically():
    g = Guard(policy(mode="enforce"))
    s = g.session()
    assert (await s.check_tool_call("issue_refund", {"amount_cents": 20000})).action == "allow"
    g.reload(policy(REFUND_CAP))
    assert (await s.check_tool_call("issue_refund", {"amount_cents": 20000})).action == "block"


def test_load_from_yaml_and_fail_fast(tmp_path):
    from gauntlet_core.schema import dump_yaml

    good = tmp_path / "p.yaml"
    good.write_text(dump_yaml(policy(REFUND_CAP)))
    assert Guard(good).policy.id == "pol_t" and Guard(str(good)).policy.version == 3
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "id: p\nrules:\n  - id: j\n    description: j\n    when: {type: judge, rubric: x}\n"
    )
    with pytest.raises(ValueError, match="judge"):
        Guard(bad)
