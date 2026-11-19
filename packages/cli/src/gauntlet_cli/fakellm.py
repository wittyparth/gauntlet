"""`--fake-llm FILE.yaml`: a stateless scripted gateway for tests and demos.

The reply for a call is a pure function of the request, so it is safe under concurrency and
after a resume: the reply index is the number of `assistant` messages already in the request
(a simulator's own earlier turns, a hosted agent's earlier model replies, a judge retry).

File format::

    cost_usd_micros: 0              # reported cost of every call
    roles:
      simulator:                    # a role, or "model:<litellm id>" for the hosted agent
        - match: "ord_1"            # substring (or list: all of them) of the request; first wins
          replies:
            - parsed: {state_note: n, action: say, message: "Where is ord_1?"}
            - parsed: {state_note: n, action: done, done_reason: goal_met}
      "model:some/model":
        - match: "ord_1"
          replies:
            - tool_calls: [{name: lookup_order, arguments: {order_id: ord_1}}]
            - "It has shipped."
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from gauntlet_core.llm import FakeLLM, FakeReply, ToolCallRequest
from gauntlet_core.llm.types import BadRequest, LLMResult
from gauntlet_core.schema import Cost, Json
from pydantic import BaseModel

__all__ = ["ScriptedLLM", "load_fake_llm"]


def _reply(item: Any, n: int) -> FakeReply:
    if isinstance(item, str):
        return FakeReply(text=item)
    calls = [
        ToolCallRequest(c.get("id", f"call_fake_{n}_{i}"), c["name"], c.get("arguments", {}))
        for i, c in enumerate(item.get("tool_calls", []))
    ]
    cost = Cost(usd_micros=int(item["cost_usd_micros"])) if "cost_usd_micros" in item else None
    return FakeReply(
        text=item.get("text", ""), tool_calls=calls, parsed=item.get("parsed"), cost=cost
    )


class ScriptedLLM:
    def __init__(self, spec: dict[str, Any]) -> None:
        self.cost = int(spec.get("cost_usd_micros", 0))
        self.roles: dict[str, list[tuple[str | list[str] | None, list[Any]]]] = {}
        for role, groups in (spec.get("roles") or {}).items():
            if groups and isinstance(groups[0], dict) and "replies" in groups[0]:
                self.roles[role] = [(g.get("match"), g["replies"]) for g in groups]
            else:
                self.roles[role] = [(None, groups)]
        self.calls: list[tuple[str, list[Json]]] = []
        self.unpriced_models: set[str] = set()

    def _pick(self, role: str, messages: list[Json]) -> FakeReply:
        groups = self.roles.get(role)
        if groups is None:
            raise BadRequest(f"fake-llm: no script for role {role!r}")
        text = "\n".join(str(m.get("content") or "") for m in messages)
        n = sum(1 for m in messages if m.get("role") == "assistant")
        for match, replies in groups:
            needles = [match] if isinstance(match, str) else (match or [])
            if all(x in text for x in needles):
                if n >= len(replies):
                    raise BadRequest(f"fake-llm: script for {role!r} exhausted at index {n}")
                return _reply(replies[n], n)
        raise BadRequest(f"fake-llm: no group of role {role!r} matches the request")

    async def complete(
        self,
        role: str,
        messages: list[Json],
        *,
        tools: list[Json] | None = None,
        response_model: type[BaseModel] | None = None,
        temperature: float | None = None,
        seed: int | None = None,
    ) -> LLMResult:
        self.calls.append((role, messages))
        reply = self._pick(role, messages)
        one = FakeLLM([reply], default_cost=Cost(usd_micros=self.cost))
        return await one.complete(
            role, messages, tools=tools, response_model=response_model, temperature=temperature
        )

    def estimate_usd_micros(
        self, role: str, messages: list[Json], *, max_output_tokens: int | None = None
    ) -> int:
        return self.cost

    async def embed(self, role: str, texts: list[str]) -> list[list[float]]:
        return await FakeLLM().embed(role, texts)


def load_fake_llm(path: Path) -> ScriptedLLM:
    return ScriptedLLM(yaml.safe_load(Path(path).read_text()) or {})
