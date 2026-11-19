import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pytest
from check_helpers import Tb, chk
from gauntlet_core.checks import (
    PrefixView,
    ProposedAction,
    evaluate_final,
    evaluate_prefix,
    get,
    names,
    register,
    text_detector,
)
from gauntlet_core.schema import CheckResult, Evidence


@register("test_digits")
@text_detector
def digits(text, params):
    return [(m.start(), m.end()) for m in re.finditer(rf"\d{{{params.get('min', 3)},}}", text)]


def test_registry_api():
    assert get("test_digits") is not None
    assert "test_digits" in names()
    assert names() == sorted(names())
    with pytest.raises(KeyError):
        get("never_registered")


def test_duplicate_registration_rejected():
    with pytest.raises(ValueError):

        @register("test_digits")
        def other(traj, params):
            return CheckResult(holds=False)


def test_text_detector_scans_messages_and_tool_args():
    t = (
        Tb()
        .agent("no numbers")
        .call("send", {"body": {"x": ["call 5551234"]}})
        .agent("ok 99")
        .build()
    )
    r = evaluate_final(chk({"type": "detector", "name": "test_digits"}), t)
    assert r.holds
    assert [(e.seq, e.quote) for e in r.evidence] == [(2, "5551234")]
    r2 = evaluate_final(chk({"type": "detector", "name": "test_digits", "params": {"min": 2}}), t)
    assert sorted(e.seq for e in r2.evidence) == [2, 4]
    clean = Tb().agent("nothing").build()
    assert not evaluate_final(chk({"type": "detector", "name": "test_digits"}), clean).holds


def test_text_detector_ignores_user_and_tool_results():
    t = Tb().user("my number is 123456").call("x", {}, result="999999").build()
    assert not evaluate_final(chk({"type": "detector", "name": "test_digits"}), t).holds


def test_custom_detector_receives_trajectory_and_params():
    @register("test_custom_count")
    def custom(traj, params):
        n = len(traj.tool_calls())
        return CheckResult(holds=n >= params["n"], evidence=[Evidence(seq=1, note=f"{n} calls")])

    t = Tb().call("a").call("b").build()
    assert evaluate_final(
        chk({"type": "detector", "name": "test_custom_count", "params": {"n": 2}}), t
    ).holds
    assert not evaluate_final(
        chk({"type": "detector", "name": "test_custom_count", "params": {"n": 3}}), t
    ).holds


def test_detector_prefix():
    c = chk({"type": "detector", "name": "test_digits"})
    tb = Tb().agent("hello")
    assert (
        evaluate_prefix(
            c, PrefixView(events=tb.events), ProposedAction(kind="agent_message", text="id 12345")
        )
        == "violates"
    )
    assert (
        evaluate_prefix(
            c, PrefixView(events=tb.events), ProposedAction(kind="agent_message", text="id 1")
        )
        == "ok"
    )
    assert (
        evaluate_prefix(
            c,
            PrefixView(events=tb.events),
            ProposedAction(kind="tool_call", tool="t", args={"a": "9999"}),
        )
        == "violates"
    )
