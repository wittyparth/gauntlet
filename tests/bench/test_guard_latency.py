"""Guard latency budget (P4-2): p99 of `check_tool_call` under 5 ms with 50 rules and a 200
event prefix. `GAUNTLET_BENCH_FACTOR` loosens the bound on shared CI runners."""

from __future__ import annotations

import os
import time

from gauntlet_core.gateway import Guard
from gauntlet_core.schema import Policy

ITERATIONS = 5_000
BUDGET_MS = 5.0


def _policy() -> Policy:
    rules = [
        {
            "id": f"r{i}",
            "description": f"rule {i}",
            "when": {
                "type": "tool_called",
                "tool": f"tool_{i}",
                "args": {"amount": {"gt": 1000 + i}},
            },
            "action": "block",
        }
        for i in range(48)
    ]
    rules.append(
        {
            "id": "taint",
            "description": "taint",
            "when": {"type": "tainted_call", "tool": "send_email"},
            "action": "block",
        }
    )
    rules.append(
        {
            "id": "egress",
            "description": "egress",
            "when": {"type": "egress", "allow_domains": ["corp.example"]},
            "action": "redact",
        }
    )
    return Policy.model_validate({"id": "bench", "rules": rules, "mode": "enforce"})


async def test_check_tool_call_p99_under_budget():
    factor = float(os.environ.get("GAUNTLET_BENCH_FACTOR", "1"))
    guard = Guard(_policy())
    session = guard.session()
    await session.record_user_message("hello")
    for i in range(66):
        await session.record_agent_message(f"step {i}")
        await session.check_tool_call(f"tool_{i % 48}", {"amount": 5}, call_id=f"c{i}")
        await session.record_tool_result(f"c{i}", f"tool_{i % 48}", {"ok": True})
    base = len(session.events)
    assert 195 <= base <= 205
    kept = session._events[:base]  # a fixed 200-event prefix for every iteration

    samples: list[float] = []
    for i in range(ITERATIONS):
        session._events = list(kept)
        t = time.perf_counter()
        d = await session.check_tool_call("lookup", {"amount": i % 900}, call_id="cx")
        samples.append((time.perf_counter() - t) * 1000)
        assert d.action == "allow"
    samples.sort()
    p50, p99 = samples[len(samples) // 2], samples[int(len(samples) * 0.99)]
    print(f"guard check_tool_call: p50={p50:.3f} ms p99={p99:.3f} ms over {ITERATIONS}")
    assert p99 < BUDGET_MS * factor, f"p99 {p99:.2f} ms over budget {BUDGET_MS * factor} ms"
