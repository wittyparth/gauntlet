from gauntlet_core.gateway.classifier import FakeClassifier, configure, split_windows, windows
from gauntlet_core.gateway.classifier.detector import detect_injection
from gauntlet_core.schema import Event, Origin, Trajectory
from gauntlet_core.world.state import WorldState  # noqa: F401


def test_window_boundaries_and_stride():
    assert windows(0, 512, 256) == []
    assert windows(10, 512, 256) == [(0, 10)]
    assert windows(512, 512, 256) == [(0, 512)]
    assert windows(513, 512, 256) == [(0, 512), (256, 513)]
    assert windows(1000, 512, 256) == [(0, 512), (256, 768), (512, 1000)]
    assert windows(10, 4, 2) == [(0, 4), (2, 6), (4, 8), (6, 10)]
    ranges = windows(2000, 100, 50)
    assert ranges[0][0] == 0 and ranges[-1][1] == 2000
    assert all(b - a <= 100 for a, b in ranges)
    assert all(ranges[i + 1][0] - ranges[i][0] == 50 for i in range(len(ranges) - 1))


def test_split_windows_overlaps_by_the_stride_complement():
    text = " ".join(f"t{i}" for i in range(10))
    wins = split_windows(text, 4, 2)
    assert wins[0] == "t0 t1 t2 t3" and wins[1] == "t2 t3 t4 t5" and wins[-1] == "t6 t7 t8 t9"
    assert split_windows("", 4, 2) == [] and split_windows("   ", 4, 2) == []


def _traj(text: str) -> Trajectory:
    from datetime import UTC, datetime

    ev = Event(
        seq=1, kind="tool_result", actor="tool", sim_time=datetime(2026, 1, 1, tzinfo=UTC),
        payload={"call_id": "c", "ok": True, "result": text},
        origin=Origin(trust="untrusted_external"),
    )  # fmt: skip
    return Trajectory.model_construct(episode_id="e", scenario=None, events=[ev])


def test_score_is_the_max_over_windows_and_evidence_is_the_best_window():
    words = [f"w{i}" for i in range(40)]
    words[30] = "EVIL"
    clf = FakeClassifier(lambda t: 0.95 if "EVIL" in t else 0.1)
    configure(clf)
    res = detect_injection(_traj(" ".join(words)), {"max_tokens": 8, "stride": 4})  # type: ignore[arg-type]
    assert (
        res.holds
        and "EVIL" in (res.evidence[0].quote or "")
        and len(res.evidence[0].quote or "") <= 200
    )
    configure(None)


def test_empty_text_is_not_scored():
    clf = FakeClassifier(lambda t: 1.0)
    configure(clf)
    res = detect_injection(_traj("   "), {})
    assert not res.holds and clf.texts_scored == 0
    configure(None)
