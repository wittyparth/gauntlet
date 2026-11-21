"""Shared helpers for the policy tests."""

from __future__ import annotations

import json
from typing import Any

from gauntlet_core.llm import FakeLLM, FakeReply
from gauntlet_server.services.jobs import run_job
from gauntlet_server.stores.jobs import PgJobQueue


def scripted_compiler() -> FakeLLM:
    """Machine rule on issue_refund for clauses not divisible by 3, a rubric otherwise."""

    def reply(messages: list[dict[str, Any]]) -> FakeReply:
        clauses = json.loads(messages[-1]["content"].split("Clauses:\n")[1])
        items = []
        for c in clauses:
            n = int(c["clause_id"][1:])
            if n % 3 == 0:
                items.append(
                    {
                        "clause_id": c["clause_id"],
                        "klass": "model",
                        "confidence": 0.8,
                        "rationale": "needs judgment",
                        "rubric": {
                            "id": "x",
                            "title": c["clause_id"],
                            "question": "q",
                            "pass_definition": "p",
                            "fail_definition": "f",
                        },
                    }
                )
            else:
                items.append(
                    {
                        "clause_id": c["clause_id"],
                        "klass": "machine",
                        "confidence": 0.9,
                        "rationale": "arg constraint",
                        "rule": {
                            "id": f"refund-{n}",
                            "description": f"refund limit {n}",
                            "when": {
                                "type": "tool_called",
                                "tool": "issue_refund",
                                "args": {"amount_cents": {"gt": 100 * n}},
                            },
                        },
                    }
                )
        return FakeReply(parsed={"items": items})

    return FakeLLM(by_role={"generator": [reply] * 4})


async def run_queue(state) -> None:
    q = PgJobQueue(state.sm)
    for lease in await q.claim("test-worker", 10, 60):
        await run_job(state, q, lease)


async def compile_seeded(client, state, name: str = "Support policy") -> dict:
    """Seed the demo pack, compile the agent's policy text, return the started job."""
    seed = (await client.post("/v1/dev/seed", json={"reset": False})).json()
    state.gateway = scripted_compiler()
    r = await client.post("/v1/policies/compile", json={"agent_id": seed["agent_id"], "name": name})
    assert r.status_code == 202, r.text
    await run_queue(state)
    return {**r.json(), "seed": seed}
