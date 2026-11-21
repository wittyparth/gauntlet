from check_helpers import Tb
from gauntlet_core.eval.cluster import failed_check_ids, failure_text
from gauntlet_core.eval.cluster.text import MAX_CHARS
from gauntlet_core.schema import Evidence, Verdict


def verdict(crit, quote="q"):
    return Verdict(
        evaluator="j", criterion=crit, result="fail", evidence=[Evidence(seq=2, quote=quote)]
    )


def traj():
    tb = Tb().user("hi").call("lookup", {"id": 1}).call("refund", {"amount": 5}).agent("done")
    tb._add("episode_ended", "platform", {"outcome": "failed", "termination": "user_done"})
    return tb.build()


CHECKS = [
    {"check_id": "success", "holds": False},
    {"check_id": "no_refund", "holds": True},
    {"check_id": "fine", "holds": False},  # a forbidden check that does not hold: not a failure
]


def test_failed_check_ids_follow_the_outcome_rule():
    assert failed_check_ids(CHECKS) == ["success", "no_refund"]


def test_includes_every_piece_in_order():
    t = failure_text(traj(), [verdict("honesty", "I lied")], CHECKS, "failed")
    parts = t.split(" | ")
    assert parts[0] == "t"  # scenario title
    assert parts[1] == "failed checks: no_refund,success"
    assert parts[2] == "failed criteria: honesty: I lied"
    assert parts[3] == "tools: lookup, refund"
    assert parts[4] == "termination: user_done (failed)"


def test_criteria_capped_at_three_and_quotes_cut_at_200():
    vs = [verdict(f"c{i}", "x" * 500) for i in range(5)]
    t = failure_text(traj(), vs, CHECKS, "failed")
    crit = t.split(" | ")[2]
    assert crit.count("c") >= 3 and "c3" not in crit and "c2" in crit
    assert max(len(p) for p in crit.removeprefix("failed criteria: ").split("; ")) <= 205


def test_whole_text_is_capped_and_deterministic():
    tb = Tb().user("hi")
    for i in range(400):
        tb.call(f"tool_number_{i}", {})
    t = tb.build()
    a = failure_text(t, [], CHECKS, "failed")
    assert len(a) == MAX_CHARS and a == failure_text(t, [], CHECKS, "failed")


def test_empty_pieces_say_none():
    t = failure_text(Tb().user("hi").build(), [], [], "failed")
    assert "failed checks: none" in t and "failed criteria: none" in t and "tools: none" in t
    assert "termination: none" in t
