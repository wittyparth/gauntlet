"""Fixture loading for the ingest tests."""

import json
from pathlib import Path

from gauntlet_core.ingest import spans_from_otlp

FIX = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "traces"
SECRETS = ["jane.doe@example.com", "4242 4242 4242 4242", "AKIAIOSFODNN7EXAMPLE", "415-555-0132"]


def load(name: str):
    return json.loads((FIX / f"{name}.json").read_text())


def spans(name: str):
    return spans_from_otlp(load(name))
