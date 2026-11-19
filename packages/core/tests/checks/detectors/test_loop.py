import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_helpers import Tb
from gauntlet_core.checks.detectors import detect_loop
from hypothesis import given
from hypothesis import strategies as st


def seqs(t):
    return [h.seq for h in detect_loop(t.build().events)]


def test_consecutive_identical_calls():
    t = Tb()
    for _ in range(3):
        t.call("search", {"q": "a", "n": 1})
    assert seqs(t) == [1, 3, 5]


def test_arg_order_is_canonical():
    t = Tb().call("s", {"a": 1, "b": 2}).call("s", {"b": 2, "a": 1}).call("s", {"a": 1, "b": 2})
    assert len(seqs(t)) == 3


def test_two_repeats_is_not_a_loop():
    assert seqs(Tb().call("s", {"q": 1}).call("s", {"q": 1})) == []


def test_different_args_break_the_run():
    t = Tb().call("s", {"q": 1}).call("s", {"q": 2}).call("s", {"q": 1}).call("s", {"q": 2})
    assert seqs(t) == []


def test_max_total_across_trajectory():
    t = Tb()
    for i in range(5):
        t.call("s", {"q": 1}).call("other", {"i": i})
    assert len(seqs(t)) == 5


def test_repeated_agent_message_normalised():
    t = (
        Tb()
        .agent("Sorry,  I can't help")
        .agent("sorry, i can't help ")
        .agent("SORRY, I CAN'T HELP")
    )
    assert seqs(t) == [1, 2, 3]


def test_no_loop_in_varied_conversation():
    t = Tb().user("hi").agent("hello").call("a").agent("done").user("thanks").agent("bye")
    assert seqs(t) == []


@given(st.lists(st.sampled_from(["user", "note"]), max_size=12))
def test_invariant_to_unrelated_events(extra):
    base = Tb()
    for _ in range(3):
        base.call("s", {"q": 1}, ok=None)
    plain = [(h.label, h.quote) for h in detect_loop(base.build().events)]
    # unrelated events interleaved between the repeated calls
    t2 = Tb()
    for _ in range(3):
        t2.call("s", {"q": 1}, ok=None)
        for k in extra:
            if k == "user":
                t2.user("x")
            else:
                t2.agent(f"m{len(t2.events)}")
    got = [(h.label, h.quote) for h in detect_loop(t2.build().events)]
    assert got == plain
