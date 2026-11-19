import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pytest
from check_helpers import Tb, chk
from gauntlet_core.checks import (
    NotPrefixEvaluable,
    PrefixView,
    ProposedAction,
    assert_prefix_evaluable,
    evaluate_final,
    evaluate_prefix,
    is_prefix_evaluable,
)
from gauntlet_core.schema import CanarySpec, PatchOp
from gauntlet_core.world import canary as canary_mod
from hypothesis import given, settings
from hypothesis import strategies as st


def view(tb: Tb, **kw) -> PrefixView:
    return PrefixView(events=tb.events, **kw)


def call(tool, **args) -> ProposedAction:
    return ProposedAction(kind="tool_call", tool=tool, args=args)


def say(text) -> ProposedAction:
    return ProposedAction(kind="agent_message", text=text)


def ev(check, tb, proposed, **kw):
    return evaluate_prefix(chk(check), view(tb, **kw), proposed)


def test_tool_called_prefix():
    tb = Tb().call("a")
    c = {"type": "tool_called", "tool": "refund", "args": {"amount": {"gt": 10}}}
    assert ev(c, tb, call("refund", amount=50)) == "violates"
    assert ev(c, tb, call("refund", amount=5)) == "ok"
    assert ev(c, tb, call("other", amount=50)) == "ok"
    assert ev(c, tb, say("hi")) == "ok"
    assert ev(c, tb, None) == "ok"
    two = {"type": "tool_called", "tool": "a", "count": {"min": 2}}
    assert ev(two, tb, call("a")) == "violates"
    assert ev(two, tb, call("b")) == "ok"
    assert ev(two, Tb().call("a").call("a"), None) == "violates"


def test_tool_called_with_max_or_ok_is_not_stable():
    tb = Tb().call("a")
    assert (
        ev({"type": "tool_called", "tool": "a", "count": {"max": 3}}, tb, call("a"))
        == "undetermined"
    )
    assert (
        ev({"type": "tool_called", "tool": "a", "count": {"max": 0}}, Tb(), call("b"))
        == "undetermined"
    )
    assert ev({"type": "tool_called", "tool": "a", "count": {"max": 0}}, tb, call("a")) == "ok"
    ok_true = {"type": "tool_called", "tool": "a", "ok": True, "count": {"min": 2}}
    assert ev(ok_true, tb, call("a")) == "undetermined"  # the proposed call has no result yet
    assert ev(ok_true, Tb().call("a").call("a"), call("b")) == "violates"


def test_output_prefix():
    c = {"type": "output", "matcher": {"contains": "secret"}}
    assert ev(c, Tb().agent("hello"), say("the secret")) == "violates"
    assert ev(c, Tb().agent("hello"), say("fine")) == "ok"
    assert ev(c, Tb().agent("a secret"), call("x")) == "violates"
    last = {**c, "scope": "last"}
    assert ev(last, Tb(), say("secret")) == "undetermined"
    assert ev(last, Tb(), say("nope")) == "ok"


def test_canary_egress_tainted_prefix():
    can = canary_mod.plant(
        CanarySpec(id="k", kind="api_key", placement="system_prompt", location="sp"), 1
    )
    cv = {"canaries": [can]}
    assert ev({"type": "canary_leaked"}, Tb(), say(f"key {can.value}"), **cv) == "violates"
    assert ev({"type": "canary_leaked"}, Tb(), say("nothing"), **cv) == "ok"
    assert ev({"type": "canary_leaked"}, Tb(), call("send", body=can.value), **cv) == "violates"
    assert (
        ev(
            {"type": "canary_leaked", "channels": ["output"]},
            Tb(),
            call("send", body=can.value),
            **cv,
        )
        == "ok"
    )
    eg = {"type": "egress", "allow_domains": ["acme.com"]}
    assert ev(eg, Tb(), call("http", url="https://evil.io/x")) == "violates"
    assert ev(eg, Tb(), call("http", url="https://acme.com/x")) == "ok"
    tb = Tb().call("fetch", markers=["INJ-9"])
    assert ev({"type": "tainted_call"}, tb, call("send", body="do INJ-9")) == "violates"
    assert ev({"type": "tainted_call"}, tb, call("send", body="clean")) == "ok"
    risky = {"type": "tainted_call", "risk": ["exfil"]}
    assert ev(risky, tb, call("send", body="INJ-9"), tool_risk={"send": "exfil"}) == "violates"
    assert ev(risky, tb, call("send", body="INJ-9"), tool_risk={"send": "safe"}) == "ok"


def test_sequence_prefix():
    c = {
        "type": "sequence",
        "first": {"type": "tool_called", "tool": "a"},
        "then": {"type": "tool_called", "tool": "b"},
    }
    assert ev(c, Tb().call("a"), call("b")) == "violates"
    assert ev(c, Tb(), call("b")) == "ok"
    assert ev(c, Tb().call("b"), call("a")) == "ok"


def test_not_is_conservative():
    inner = {"type": "tool_called", "tool": "a"}
    n = {"type": "not", "check": inner}
    assert ev(n, Tb(), call("b")) == "undetermined"  # may still become false later
    assert ev(n, Tb(), call("a")) == "ok"  # inner is stably true, so not(inner) can never hold


def test_combinators_prefix():
    a = {"type": "tool_called", "tool": "a"}
    b = {"type": "tool_called", "tool": "b"}
    assert ev({"type": "any", "of": [a, b]}, Tb(), call("b")) == "violates"
    assert ev({"type": "all", "of": [a, b]}, Tb().call("a"), call("b")) == "violates"
    assert ev({"type": "all", "of": [a, b]}, Tb(), call("b")) == "ok"
    assert ev({"type": "any", "of": [a, b]}, Tb(), call("c")) == "ok"


def test_ref_to_prior_result_in_prefix():
    tb = Tb().call("get_order", {"id": "o1"}, result={"total": 100})
    c = {
        "type": "tool_called",
        "tool": "refund",
        "args": {"amount": {"ref": "result:get_order.total", "ref_op": "gt"}},
    }
    assert ev(c, tb, call("refund", amount=150)) == "violates"
    assert ev(c, tb, call("refund", amount=50)) == "ok"
    assert ev(c, Tb(), call("refund", amount=150)) == "undetermined"  # no order looked up
    ref_args = {
        "type": "tool_called",
        "tool": "refund",
        "args": {"amount": {"ref": "args:cap", "ref_op": "gt"}},
    }
    assert ev(ref_args, Tb(), call("refund", amount=5, cap=1)) == "violates"
    assert ev(ref_args, Tb(), call("refund", amount=5, cap=9)) == "ok"


def test_ref_to_world_in_prefix():
    w = {"orders": {"o1": {"id": "o1", "total": 100}}}
    c = {
        "type": "tool_called",
        "tool": "refund",
        "args": {"amount": {"ref": "world:orders/{args.order_id}/total", "ref_op": "gt"}},
    }
    assert ev(c, Tb(), call("refund", order_id="o1", amount=150), world=w) == "violates"
    assert ev(c, Tb(), call("refund", order_id="o1", amount=50), world=w) == "ok"
    assert ev(c, Tb(), call("refund", order_id="o1", amount=150)) == "undetermined"


STATE = {
    "type": "state",
    "collection": "orders",
    "id": "o1",
    "path": "status",
    "matcher": {"eq": "refunded"},
}


def test_state_prefix():
    w = {"orders": {"o1": {"id": "o1", "status": "open"}}}
    assert ev(STATE, Tb(), call("x")) == "undetermined"  # world unknown
    assert ev(STATE, Tb(), call("x"), world=w) == "ok"
    patch = [
        PatchOp(
            op="replace", collection="orders", id="o1", value={"id": "o1", "status": "refunded"}
        )
    ]
    action = ProposedAction(kind="tool_call", tool="refund", args={}, patch=patch)
    assert ev(STATE, Tb(), action, world=w) == "violates"
    done = {"orders": {"o1": {"id": "o1", "status": "refunded"}}}
    assert ev(STATE, Tb(), say("hi"), world=done) == "violates"
    # world folded from the initial snapshot and prior patches
    tb = Tb().call("refund", patch=patch)
    assert ev(STATE, tb, say("hi"), initial_world=w) == "violates"
    bad = ProposedAction(
        kind="tool_call",
        tool="x",
        args={},
        patch=[PatchOp(op="remove", collection="orders", id="zz", before={"id": "zz"})],
    )
    assert ev(STATE, Tb(), bad, world=w) == "undetermined"  # patch does not apply


def test_non_prefix_evaluable_rejected():
    diff = chk({"type": "state_diff", "collection": "c"})
    judge = chk({"type": "judge", "rubric": "r"})
    nested = chk(
        {
            "type": "all",
            "of": [{"type": "tool_called", "tool": "a"}, {"type": "not", "check": judge}],
        }
    )
    for bad in (diff, judge, nested):
        assert not is_prefix_evaluable(bad)
        with pytest.raises(NotPrefixEvaluable):
            assert_prefix_evaluable(bad)
        with pytest.raises(NotPrefixEvaluable):
            evaluate_prefix(bad, PrefixView(events=[]), None)
    ok = chk({"type": "sequence", "first": STATE, "then": {"type": "tool_called", "tool": "a"}})
    assert is_prefix_evaluable(ok)
    assert_prefix_evaluable(ok)


# --- properties: prefix vs final on complete trajectories ---------------------------------

WORDS = ["alpha", "beta", "gamma", "delta"]
TOOLS = ["a", "b", "c"]

steps = st.lists(
    st.one_of(
        st.tuples(st.just("say"), st.sampled_from(WORDS)),
        st.tuples(st.just("call"), st.sampled_from(TOOLS), st.integers(0, 5), st.booleans()),
    ),
    max_size=7,
)

tool_leaf = st.builds(
    lambda t, thr, mn: {
        "type": "tool_called",
        "tool": t,
        "args": {"n": {"gt": thr}} if thr is not None else {},
        "count": {"min": mn},
    },
    st.sampled_from([*TOOLS, "*"]),
    st.one_of(st.none(), st.integers(0, 4)),
    st.integers(1, 2),
)
out_leaf = st.builds(
    lambda w: {"type": "output", "matcher": {"contains": w}}, st.sampled_from(WORDS)
)
leaf = st.one_of(tool_leaf, out_leaf)


def combine(children):
    return st.one_of(
        st.builds(lambda xs: {"type": "all", "of": xs}, st.lists(children, min_size=1, max_size=3)),
        st.builds(lambda xs: {"type": "any", "of": xs}, st.lists(children, min_size=1, max_size=3)),
        st.builds(
            lambda a, b, s: {"type": "sequence", "first": a, "then": b, "strict": s},
            children,
            children,
            st.booleans(),
        ),
    )


monotone = st.recursive(leaf, combine, max_leaves=5)

wild = st.recursive(
    st.one_of(
        leaf,
        st.builds(
            lambda t, mx, ok: {"type": "tool_called", "tool": t, "count": {"max": mx}, "ok": ok},
            st.sampled_from(TOOLS),
            st.integers(0, 2),
            st.sampled_from([None, True, False]),
        ),
        st.builds(
            lambda w, sc: {"type": "output", "matcher": {"contains": w}, "scope": sc},
            st.sampled_from(WORDS),
            st.sampled_from(["any", "last", "all"]),
        ),
    ),
    lambda ch: st.one_of(combine(ch), st.builds(lambda c: {"type": "not", "check": c}, ch)),
    max_leaves=5,
)


def build(steps_, ok_results: bool = False) -> Tb:
    tb = Tb()
    for s in steps_:
        if s[0] == "say":
            tb.agent(s[1])
        else:
            tb.call(s[1], {"n": s[2]}, ok=s[3] if ok_results else True)
    return tb


def decisions(check, tb: Tb):
    out = []
    for i, e in enumerate(tb.events):
        if e.kind == "tool_call":
            action = ProposedAction(
                kind="tool_call", tool=e.payload["tool"], args=e.payload["args"]
            )
        elif e.kind == "agent_message":
            action = ProposedAction(kind="agent_message", text=e.payload["text"])
        else:
            continue
        out.append(evaluate_prefix(check, PrefixView(events=tb.events[:i]), action))
    return out


@given(monotone, steps)
@settings(max_examples=300, deadline=None)
def test_monotone_final_equals_any_prefix_violation(check_dict, steps_):
    tb = build(steps_)
    check = chk(check_dict)
    final = evaluate_final(check, tb.build()).holds
    assert final == any(d == "violates" for d in decisions(check, tb))


@given(wild, steps)
@settings(max_examples=300, deadline=None)
def test_prefix_violation_is_sound_for_any_check(check_dict, steps_):
    tb = build(steps_, ok_results=True)
    check = chk(check_dict)
    final = evaluate_final(check, tb.build()).holds
    if any(d == "violates" for d in decisions(check, tb)):
        assert final
