import importlib.util
from pathlib import Path

import pytest
from gauntlet_core.gateway.classifier import (
    ClassifierUnavailable,
    FakeClassifier,
    OnnxClassifier,
    TorchClassifier,
    evaluate_classifier,
)

BUILD = Path(__file__).resolve().parents[5] / "tests" / "fixtures" / "classifier_eval" / "build.py"


def corpus():
    spec = importlib.util.spec_from_file_location("classifier_eval_build", BUILD)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_evaluate_classifier_on_known_scores():
    pos = [f"p{i}" for i in range(100)]
    neg = [f"n{i}" for i in range(200)]
    scores = {p: 0.5 + i / 400 for i, p in enumerate(pos)}
    scores.update({n: i / 800 for i, n in enumerate(neg)})
    res = evaluate_classifier(FakeClassifier(lambda t: scores[t]), pos, neg)
    assert res["n_pos"] == 100 and res["n_neg"] == 200
    assert res["tpr_at_fpr_1pct"] == 1.0 and res["auc"] == 1.0
    # at most 1 percent of 200 negatives (2) may score at or above the threshold
    assert sum(1 for n in neg if scores[n] >= res["threshold_at_fpr_1pct"]) <= 2


def test_evaluate_with_ties():
    res = evaluate_classifier(FakeClassifier(lambda t: 0.5), ["a"] * 10, ["b"] * 100)
    assert res["auc"] == 0.5 and res["tpr_at_fpr_1pct"] == 0.0  # nothing separates them


def test_corpus_is_deterministic_and_authors_no_attack_text():
    b = corpus()
    p1, n1 = b.build(7)
    p2, n2 = b.build(7)
    assert (p1, n1) == (p2, n2) and p1 != b.build(8)[0]
    assert 0 < len(p1) <= b.MAX_POSITIVES and len(n1) >= b.NEUTRAL
    assert not any("ignore previous instructions" in n.lower() for n in n1)


def test_fake_on_the_corpus():
    b = corpus()
    pos, neg = b.build()
    clf = FakeClassifier(lambda t: 1.0 if "ZX-4417" in t or "evil.example" in t else 0.0)
    res = evaluate_classifier(clf, pos, neg)
    assert res["n_pos"] == len(pos) and res["auc"] >= 0.5


def test_real_backends_fail_cleanly_without_the_extra(tmp_path):
    with pytest.raises(ClassifierUnavailable):
        OnnxClassifier(tmp_path)  # no extra, or no exported model: never a download
    if importlib.util.find_spec("transformers") is None:
        with pytest.raises(ClassifierUnavailable):
            TorchClassifier("x/y")
