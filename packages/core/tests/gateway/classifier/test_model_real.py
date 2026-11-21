"""Real-model evaluation. Skipped unless GAUNTLET_CLASSIFIER_TEST=1 and the model was exported
once with tools/export_classifier.py (the test itself never downloads anything)."""

import importlib.util
import os
from pathlib import Path

import pytest
from gauntlet_core.gateway.classifier import OnnxClassifier, evaluate_classifier
from gauntlet_core.gateway.classifier.model import cache_dir

pytestmark = pytest.mark.skipif(
    os.environ.get("GAUNTLET_CLASSIFIER_TEST") != "1", reason="set GAUNTLET_CLASSIFIER_TEST=1"
)
BUILD = Path(__file__).resolve().parents[5] / "tests" / "fixtures" / "classifier_eval" / "build.py"
# Set from the first measured value minus a margin once it exists; 0.0 means "not yet measured".
MIN_TPR_AT_FPR_1PCT = 0.0


def test_tpr_at_one_percent_fpr():
    spec = importlib.util.spec_from_file_location("classifier_eval_build", BUILD)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    pos, neg = mod.build()
    res = evaluate_classifier(OnnxClassifier(cache_dir()), pos, neg)
    print(f"classifier eval: {res}")
    assert res["tpr_at_fpr_1pct"] >= MIN_TPR_AT_FPR_1PCT
