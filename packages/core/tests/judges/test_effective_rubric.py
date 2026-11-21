from gauntlet_core.judges import CalibrationState, effective_rubric
from judge_helpers import rubric


def test_no_calibration_keeps_the_document_defaults():
    r = rubric(threshold=0.8)
    assert effective_rubric(r, None) is r


def test_calibrated_values_are_applied_to_a_copy():
    r = rubric(threshold=0.8)
    out = effective_rubric(r, CalibrationState(r.version, 0.6, True))
    assert (out.threshold, out.gating_allowed) == (0.6, True)
    assert (r.threshold, r.gating_allowed) == (0.8, False)  # the document is untouched


def test_always_escalate_threshold_is_capped_at_one():
    r = rubric()
    assert effective_rubric(r, CalibrationState(r.version, 1.01, True)).threshold == 1.0


def test_stale_or_other_version_never_allows_gating():
    r = rubric(threshold=0.8, gating_allowed=True)
    stale = effective_rubric(r, CalibrationState(r.version, 0.5, True, stale=True))
    assert not stale.gating_allowed and stale.threshold == 0.8
    other = effective_rubric(r, CalibrationState(r.version + 1, 0.5, True))
    assert not other.gating_allowed and other.threshold == 0.8
