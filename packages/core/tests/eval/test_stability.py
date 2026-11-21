import pytest
from gauntlet_core.eval.stability import (
    AdaptiveScheduler,
    ScenarioRunSummary,
    adaptive_decision,
    classify_flaky,
    suggest_quarantine,
)


@pytest.mark.parametrize(
    "trials, flaky, flakiness",
    [
        ([True, True], False, None),  # fewer than 3 trials
        ([True, True, True], False, 0.0),
        ([False, False, False], False, 0.0),
        ([True, False, True], True, pytest.approx(1 - abs(2 * 2 / 3 - 1))),
        ([True, False, True, False], True, 1.0),  # a coin flip
        ([True, True, True, True, False], True, pytest.approx(0.4)),
    ],
)
def test_classify_flaky_table(trials, flaky, flakiness):
    r = classify_flaky(trials)
    assert r.flaky is flaky and r.flakiness == flakiness


def run(i, flaky=False, outcomes=("passed",) * 3):
    return ScenarioRunSummary(run_id=f"r{i}", flaky=flaky, outcomes=tuple(outcomes))


def test_three_of_last_five_flaky_suggests_quarantine():
    # newest first
    history = [run(0, True), run(1), run(2, True), run(3), run(4, True), run(5, True)]
    s = suggest_quarantine(history)
    assert s is not None and s.kind == "flaky" and "3 of the last 5" in s.reason


def test_two_of_five_does_not():
    assert suggest_quarantine([run(0, True), run(1), run(2, True), run(3), run(4)]) is None


def test_flaky_older_than_five_runs_does_not_count():
    assert suggest_quarantine([*[run(i) for i in range(5)], run(5, True), run(6, True)]) is None


def test_simulator_errors_three_of_ten_suggests_quarantine():
    ok = ("passed",) * 7
    s = suggest_quarantine([run(0, outcomes=ok + ("simulator_error",) * 3)])
    assert s is not None and s.kind == "simulator_errors" and "3 of the last 10" in s.reason
    two = ok + ("simulator_error",) * 2 + ("passed",)
    assert suggest_quarantine([run(0, outcomes=two)]) is None
    assert suggest_quarantine([run(0, outcomes=("simulator_error",) * 3)]) is None  # too few


def test_adaptive_decision_rules():
    # L4's rule: stop when P(p > 0.9) > 0.95 (28 straight passes) or P(p < 0.5) > 0.95 (4 fails)
    assert adaptive_decision(passed=3, counted=3, excluded=0, repetitions=10) == "continue"
    assert adaptive_decision(passed=28, counted=28, excluded=0, repetitions=40) == "stop"
    assert adaptive_decision(passed=0, counted=3, excluded=0, repetitions=10) == "continue"
    assert adaptive_decision(passed=0, counted=4, excluded=0, repetitions=10) == "stop"
    assert adaptive_decision(passed=2, counted=3, excluded=0, repetitions=10) == "continue"
    assert adaptive_decision(passed=5, counted=10, excluded=0, repetitions=10) == "stop"  # max
    assert adaptive_decision(passed=0, counted=0, excluded=1, repetitions=10) == "continue"
    # excluded outcomes are not trials but count toward the repetitions + 2 episode cap
    assert adaptive_decision(passed=0, counted=0, excluded=12, repetitions=10) == "stop"
    assert adaptive_decision(passed=1, counted=2, excluded=10, repetitions=10) == "stop"


def test_scheduler_failing_scenario_stops_at_four_and_passing_runs_to_the_maximum():
    s = AdaptiveScheduler(repetitions=6)
    assert s.start(["bad", "good"]) == {"bad": 3, "good": 3}
    for _ in range(2):  # two of three finished: nothing decided yet
        assert s.record("bad", "failed") is None
    assert s.record("bad", "failed") == 3  # all three done and 0/3: P(p<.5) = .94, go on
    assert s.record("bad", "failed") is None  # 0/4: stop
    for _ in range(2):
        assert s.record("good", "passed") is None
    assert [s.record("good", "passed"), s.record("good", "passed"), s.record("good", "passed")] == [
        3, 4, 5,
    ]  # fmt: skip
    assert s.record("good", "passed") is None  # six counted trials: the maximum


def test_scheduler_excluded_outcomes_respect_the_hard_cap():
    s = AdaptiveScheduler(repetitions=3)
    s.start(["x"])
    reps = [s.record("x", "simulator_error") for _ in range(3)]
    assert reps == [None, None, 3]  # 3 excluded, 0 counted: one more try
    assert s.record("x", "simulator_error") == 4  # 4 excluded < 3 + 2
    assert s.record("x", "simulator_error") is None  # 5 episodes: the cap
