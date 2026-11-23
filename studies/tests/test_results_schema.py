from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from studies.common import RESULTS_DIR, StudyResult, bootstrap_mean, load_results


def _make(**kw):
    base = dict(
        name="x", seed=1, platform_version="0.1.0", started_at=datetime(2026, 1, 1, tzinfo=UTC),
        metrics={"a": 0.5}, intervals={"a": (0.4, 0.6)}, n=10, limitations=["l"],
    )  # fmt: skip
    return StudyResult(**{**base, **kw})


def test_every_committed_result_validates():
    for p in RESULTS_DIR.glob("*.json"):
        r = StudyResult.model_validate_json(p.read_text())
        assert r.seed is not None and r.platform_version
    assert len(load_results()) == len(list(RESULTS_DIR.glob("*.json")))


def test_interval_must_bracket_metric():
    with pytest.raises(ValidationError):
        _make(intervals={"a": (0.6, 0.7)})


def test_interval_for_unknown_metric_and_missing_limitations_rejected():
    with pytest.raises(ValidationError):
        _make(intervals={"zzz": (0.0, 1.0)})
    with pytest.raises(ValidationError):
        _make(limitations=[])


def test_bootstrap_brackets_mean_and_is_seeded():
    vals = [1.0, 2.0, 3.0, 10.0]
    m, lo, hi = bootstrap_mean(vals, seed=3)
    assert lo <= m <= hi and (m, lo, hi) == bootstrap_mean(vals, seed=3)
    assert bootstrap_mean([], seed=0) == (0.0, 0.0, 0.0)
