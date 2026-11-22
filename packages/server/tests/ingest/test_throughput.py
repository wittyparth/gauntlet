"""Ingest throughput (P5-1): recorded, not gating (hardware varies); the target is 500 spans
per second on one api process."""

from __future__ import annotations

import time

import pytest
from ingest_helpers import build

pytestmark = pytest.mark.integration
SPANS = 1200


async def test_ingest_throughput_is_recorded(client):
    b = build()
    spans = []
    for i in range(SPANS // 3):
        t = f"{i:032x}"
        llm = {"openinference.span.kind": "LLM", "session.id": f"load-{i}"}
        llm.update(b.oi_llm({0: ("user", f"hello {i}")}, ("assistant", "hi")))
        tool = {"openinference.span.kind": "TOOL", "tool.name": "lookup", "input.value": "{}",
                "output.value": "ok"}  # fmt: skip
        spans += [
            b.span(t, f"{i:016x}", "llm", 0, 10, llm),
            b.span(t, f"{i + 10**6:016x}", "lookup", 12, 20, tool),
            b.span(
                t, f"{i + 2 * 10**6:016x}", "agent", 0, 30, {"openinference.span.kind": "AGENT"}
            ),
        ]
    started = time.perf_counter()
    r = await client.post("/v1/traces", json=b.doc(spans))
    rate = SPANS / (time.perf_counter() - started)
    assert r.status_code == 200
    print(f"ingest throughput: {rate:.0f} spans/s (target 500)")
    stats = (await client.get("/v1/production/stats")).json()
    assert stats["spans"] == SPANS and stats["conversations"] == SPANS // 3
