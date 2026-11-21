"""Prompt-injection classifier detector and origin rules (P4-4). Importing this package
registers the `injection_classifier` detector; no model is loaded or downloaded."""

from .detector import DETECTOR_NAME, configure, detect_injection, split_windows, warm_up, windows
from .eval import evaluate_classifier
from .model import (
    ClassifierUnavailable,
    FakeClassifier,
    InjectionClassifier,
    OnnxClassifier,
    TorchClassifier,
    default_classifier,
)
from .origin import DEFAULT_ORIGIN_RULES, OriginRule, OriginRules

__all__ = [
    "DEFAULT_ORIGIN_RULES",
    "DETECTOR_NAME",
    "ClassifierUnavailable",
    "FakeClassifier",
    "InjectionClassifier",
    "OnnxClassifier",
    "OriginRule",
    "OriginRules",
    "TorchClassifier",
    "configure",
    "default_classifier",
    "detect_injection",
    "evaluate_classifier",
    "split_windows",
    "warm_up",
    "windows",
]
