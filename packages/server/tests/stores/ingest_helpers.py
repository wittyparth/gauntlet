"""Helpers for the ingest tests: OTLP documents from the shared fixtures and the builder."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

FIX = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "traces"
SECRETS = ["jane.doe@example.com", "4242 4242 4242 4242", "AKIAIOSFODNN7EXAMPLE", "415-555-0132"]


def build():
    spec = importlib.util.spec_from_file_location("trace_fixture_build", FIX / "build.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIX / f"{name}.json").read_text())


def session_doc(session: str, n_turns: int = 1, trace: str | None = None) -> dict[str, Any]:
    """A small conversation: n user turns, each answered, under `session`."""
    b = build()
    t = trace or (session.encode().hex() + "0" * 32)[:32]
    spans = []
    for i in range(n_turns):
        attrs = {"openinference.span.kind": "LLM", "session.id": session}
        attrs.update(
            b.oi_llm({0: ("user", f"question {i} in {session}")}, ("assistant", f"answer {i}"))
        )
        sid = f"{session[:6]}{i:02d}".ljust(16, "0")[:16]
        spans.append(b.span(t, sid, "llm", i * 100, i * 100 + 10, attrs))
    return b.doc(spans)


async def post(client, doc: dict[str, Any], **params):
    return await client.post("/v1/traces", json=doc, params=params)
