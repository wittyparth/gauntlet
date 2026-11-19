import re

from gauntlet_core.ids import new_id


def test_prefix_and_length():
    i = new_id("run")
    assert re.fullmatch(r"run_[0-9A-HJKMNP-TV-Z]{26}", i)


def test_sortable_by_creation_time():
    t = iter(range(1_700_000_000_000, 1_700_000_000_100))
    ids = [new_id("ep", now_ms=lambda: next(t)) for _ in range(100)]
    assert ids == sorted(ids)


def test_monotonic_in_one_millisecond():
    ids = [new_id("x", now_ms=lambda: 1_800_000_000_000) for _ in range(10_000)]
    assert ids == sorted(ids) and len(set(ids)) == 10_000


def test_no_collisions():
    assert len({new_id("c") for _ in range(100_000)}) == 100_000


def test_clock_stepping_back_stays_monotonic():
    a = new_id("x", now_ms=lambda: 2_000_000_000_000)
    b = new_id("x", now_ms=lambda: 1_000_000_000_000)
    assert a < b
