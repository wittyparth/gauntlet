from pathlib import Path

import gauntlet_core.eval.rubrics as pkg
import pytest
from gauntlet_core.eval import load_rubrics

IDS = [
    "binding_commitment",
    "escalation_correctness",
    "groundedness",
    "hallucinated_policy",
    "policy_adherence",
    "task_completion",
    "tone_empathy",
]
SEVERITY = {
    "task_completion": "medium",
    "groundedness": "high",
    "policy_adherence": "high",
    "hallucinated_policy": "high",
    "binding_commitment": "high",
    "tone_empathy": "low",
    "escalation_correctness": "medium",
}


def test_seven_files_load_and_ids_match_file_names():
    rubrics = load_rubrics()
    assert sorted(rubrics) == IDS
    files = sorted(p.stem for p in Path(pkg.__file__).parent.glob("*.yaml"))
    assert files == IDS and all(k == r.id for k, r in rubrics.items())


def test_examples_cover_pass_and_fail_and_are_short():
    for r in load_rubrics().values():
        assert 3 <= len(r.examples) <= 5, r.id
        results = {e.result for e in r.examples}
        assert {"pass", "fail"} <= results, r.id
        assert r.na_definition and "na" in results, r.id
        for e in r.examples:
            lines = e.transcript.splitlines()
            assert len(lines) <= 8 and all(line.startswith("[") for line in lines), r.id


def test_severity_and_flags_match_table():
    for rid, r in load_rubrics().items():
        assert r.severity == SEVERITY[rid]
        assert r.hard_fail is False and r.gating_allowed is False
        assert r.scope == "conversation" and r.threshold == 0.8


def test_subset_and_unknown():
    assert list(load_rubrics(["tone_empathy"])) == ["tone_empathy"]
    with pytest.raises(KeyError):
        load_rubrics(["nope"])


def test_no_forbidden_model_vendor_ids_in_library():
    for p in Path(pkg.__file__).parent.glob("*.yaml"):
        text = p.read_text()
        assert "openai/" not in text and "anthropic/" not in text


def test_policy_adherence_v2_checks_identity_order_and_other_rules():
    r = load_rubrics(["policy_adherence"])["policy_adherence"]
    assert r.version == 2
    text = r.fail_definition.lower()
    for needle in (
        "both the order id",
        "wrong identity",
        "invented",
        "escalat",
        "only the order status",
    ):
        assert needle in text
    assert any(e.result == "fail" and "email" in e.why for e in r.examples)
