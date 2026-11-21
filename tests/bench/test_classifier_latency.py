"""Classifier latency per 512-token window (P4-4). Records the number; a miss is a printed
report, not a failure, because hardware varies. Needs GAUNTLET_CLASSIFIER_TEST=1."""

import os
import time

import pytest
from gauntlet_core.gateway.classifier import OnnxClassifier
from gauntlet_core.gateway.classifier.model import cache_dir

pytestmark = pytest.mark.skipif(
    os.environ.get("GAUNTLET_CLASSIFIER_TEST") != "1", reason="set GAUNTLET_CLASSIFIER_TEST=1"
)
TARGET_P95_MS = 30.0


def test_p95_per_512_token_window():
    clf = OnnxClassifier(cache_dir())
    text = " ".join(f"word{i}" for i in range(450))
    clf.score([text])  # warm up
    samples = []
    for _ in range(100):
        t = time.perf_counter()
        clf.score([text])
        samples.append((time.perf_counter() - t) * 1000)
    samples.sort()
    p95 = samples[94]
    print(f"classifier p95 per window: {p95:.1f} ms (target {TARGET_P95_MS} ms)")
    if p95 > TARGET_P95_MS:
        pytest.skip(f"report only: p95 {p95:.1f} ms is above the {TARGET_P95_MS} ms target")
