# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Prompt-injection classifiers behind one Protocol (P4-4).

Model choice (CQ-G7; verify licence and availability on the model card before shipping, and
record it in NOTICES). The default is `protectai/deberta-v3-base-prompt-injection-v2`, a
DeBERTa-v3-base binary classifier (Apache-2.0 per its card). Alternatives to evaluate: Meta
Prompt Guard 2 (Llama licence, gated: check the terms) and `deepset/deberta-v3-base-injection`
(check the licence). The model id and revision are configuration, never hardcoded in logic:
`GAUNTLET_CLASSIFIER_MODEL`, `GAUNTLET_CLASSIFIER_REVISION`.

The classifier is an opt-in extra (`gauntlet-core[classifier]`, or `classifier-torch`). It is
never part of the default install and nothing here downloads a model: the ONNX export is a
one-time offline step (`tools/export_classifier.py`).
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

__all__ = [
    "DEFAULT_MODEL",
    "ClassifierUnavailable",
    "FakeClassifier",
    "InjectionClassifier",
    "OnnxClassifier",
    "TorchClassifier",
    "cache_dir",
    "default_classifier",
]

DEFAULT_MODEL = "protectai/deberta-v3-base-prompt-injection-v2"


class ClassifierUnavailable(RuntimeError):
    """The optional dependency or the exported model is missing."""


class InjectionClassifier(Protocol):
    def score(self, texts: Sequence[str]) -> list[float]:
        """Probability, per text, that it is a prompt injection."""
        ...


class FakeClassifier:
    """For tests: `fn(text) -> probability`; counts calls and scored texts."""

    def __init__(self, fn: Callable[[str], float]) -> None:
        self.fn = fn
        self.calls = 0
        self.texts_scored = 0

    def score(self, texts: Sequence[str]) -> list[float]:
        self.calls += 1
        self.texts_scored += len(texts)
        return [float(self.fn(t)) for t in texts]


def cache_dir(revision: str | None = None) -> Path:
    rev = revision or os.environ.get("GAUNTLET_CLASSIFIER_REVISION", "main")
    return Path.home() / ".cache" / "gauntlet" / "classifier" / rev


class OnnxClassifier:
    """CPU ONNX runtime (primary path). `model_dir` holds `model.onnx` and the tokenizer files
    written by `tools/export_classifier.py`. Needs the `classifier` extra."""

    def __init__(self, model_dir: str | Path, *, threads: int = 2, max_length: int = 512) -> None:
        try:
            import numpy as np
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError as e:
            raise ClassifierUnavailable(
                "install the `classifier` extra (onnxruntime, tokenizers, numpy)"
            ) from e
        d = Path(model_dir)
        if not (d / "model.onnx").is_file() or not (d / "tokenizer.json").is_file():
            raise ClassifierUnavailable(
                f"{d}: no exported model; run tools/export_classifier.py once (offline step)"
            )
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        self._np = np
        self._session = ort.InferenceSession(
            str(d / "model.onnx"), opts, providers=["CPUExecutionProvider"]
        )
        self._tok = Tokenizer.from_file(str(d / "tokenizer.json"))
        self._tok.enable_truncation(max_length)
        self._tok.enable_padding()
        self._inputs = {i.name for i in self._session.get_inputs()}

    def score(self, texts: Sequence[str]) -> list[float]:
        if not texts:
            return []
        np = self._np
        enc = self._tok.encode_batch(list(texts))
        feeds = {
            "input_ids": np.array([e.ids for e in enc], dtype=np.int64),
            "attention_mask": np.array([e.attention_mask for e in enc], dtype=np.int64),
        }
        feeds = {k: v for k, v in feeds.items() if k in self._inputs}
        logits = self._session.run(None, feeds)[0]
        z = logits - logits.max(axis=-1, keepdims=True)
        probs = np.exp(z) / np.exp(z).sum(axis=-1, keepdims=True)
        return [float(p[-1]) for p in probs]  # the last class is "injection"


class TorchClassifier:
    """Fallback behind the `classifier-torch` extra (transformers + torch)."""

    def __init__(self, model_name: str | None = None, *, revision: str | None = None) -> None:
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as e:
            raise ClassifierUnavailable("install the `classifier-torch` extra") from e
        name = model_name or os.environ.get("GAUNTLET_CLASSIFIER_MODEL", DEFAULT_MODEL)
        rev = revision or os.environ.get("GAUNTLET_CLASSIFIER_REVISION") or None
        self._torch = torch
        self._tok = AutoTokenizer.from_pretrained(name, revision=rev)
        self._model = AutoModelForSequenceClassification.from_pretrained(name, revision=rev).eval()

    def score(self, texts: Sequence[str]) -> list[float]:
        if not texts:
            return []
        batch = self._tok(
            list(texts), return_tensors="pt", truncation=True, max_length=512, padding=True
        )
        with self._torch.no_grad():
            probs = self._torch.softmax(self._model(**batch).logits, dim=-1)
        return [float(p[-1]) for p in probs]


def default_classifier() -> InjectionClassifier:
    """The ONNX classifier from the cache directory; raises ClassifierUnavailable."""
    return OnnxClassifier(cache_dir())
