# Classifier evaluation corpus

`build.py` builds a deterministic, seeded corpus for the prompt-injection classifier:
library attacks (vector `tool_result` or `document`, placeholders filled with fixed fake
values, wrapped in benign pack text) as positives; benign pack texts plus 200 seeded
neutral paragraphs as negatives. No attack text is authored here.

Run `GAUNTLET_CLASSIFIER_TEST=1 uv run pytest packages/core/tests/gateway/classifier/test_model_real.py -s`
after exporting the model once (`tools/export_classifier.py`).
