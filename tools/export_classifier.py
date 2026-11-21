"""One-time, offline export of the injection classifier to ONNX (P4-4).

    uv run --with optimum[onnxruntime] --with transformers --with torch \\
        python tools/export_classifier.py [--model ID] [--revision COMMIT_SHA]

Downloads the model once (this is the only step that touches the network), writes
`~/.cache/gauntlet/classifier/<revision>/{model.onnx,tokenizer.json,...}` and prints the
revision. Pin the revision with GAUNTLET_CLASSIFIER_REVISION. Check the model card's licence
first and record it in NOTICES.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

DEFAULT_MODEL = "protectai/deberta-v3-base-prompt-injection-v2"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=os.environ.get("GAUNTLET_CLASSIFIER_MODEL", DEFAULT_MODEL))
    ap.add_argument("--revision", default=os.environ.get("GAUNTLET_CLASSIFIER_REVISION"))
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    try:
        from huggingface_hub import model_info
        from optimum.onnxruntime import ORTModelForSequenceClassification
        from transformers import AutoTokenizer
    except ImportError as e:
        print(f"missing export dependency: {e}", file=sys.stderr)
        return 2
    revision = a.revision or model_info(a.model).sha
    out = a.out or Path.home() / ".cache" / "gauntlet" / "classifier" / str(revision)
    out.mkdir(parents=True, exist_ok=True)
    model = ORTModelForSequenceClassification.from_pretrained(
        a.model, revision=revision, export=True
    )
    model.save_pretrained(out)
    AutoTokenizer.from_pretrained(a.model, revision=revision).save_pretrained(out)
    # `OnnxClassifier` looks for model.onnx and tokenizer.json
    print(f"exported {a.model}@{revision} to {out}")
    print(f"export GAUNTLET_CLASSIFIER_REVISION={revision}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
