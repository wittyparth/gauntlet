"""FakeLLM: a scripted Gateway for tests. No network, records every call."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from gauntlet_core.schema import Cost, Json

from .embed import HashEmbedder
from .types import GatewayError, LLMResult, StructuredOutputError, ToolCallRequest


@dataclass
class FakeReply:
    text: str = ""
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    parsed: Json | BaseModel | None = None
    cost: Cost | None = None
    error: GatewayError | None = None


Scripted = str | FakeReply | Callable[[list[Json]], "str | FakeReply"]


@dataclass
class CallRecord:
    role: str
    messages: list[Json]
    tools: list[Json] | None
    response_model: type[BaseModel] | None


class FakeLLM:
    def __init__(
        self,
        script: list[Scripted] | None = None,
        *,
        by_role: dict[str, list[Scripted]] | None = None,
        default_cost: Cost | None = None,
    ) -> None:
        self._queues: dict[str | None, list[Scripted]] = {None: list(script or [])}
        for role, s in (by_role or {}).items():
            self._queues[role] = list(s)
        self._pos: dict[str | None, int] = dict.fromkeys(self._queues, 0)
        self.default_cost = default_cost or Cost()
        self.calls: list[CallRecord] = []
        self.scales: list[int] = []

    def _queue_key(self, role: str) -> str | None:
        return role if role in self._queues else None

    async def complete(
        self,
        role: str,
        messages: list[Json],
        *,
        tools: list[Json] | None = None,
        response_model: type[BaseModel] | None = None,
        temperature: float | None = None,
        seed: int | None = None,
        max_output_scale: int = 1,
    ) -> LLMResult:
        self.scales.append(max_output_scale)
        self.calls.append(CallRecord(role, list(messages), tools, response_model))
        key = self._queue_key(role)
        i = self._pos[key]
        queue = self._queues[key]
        if i >= len(queue):
            raise AssertionError(f"FakeLLM script exhausted at call {i}")
        self._pos[key] = i + 1
        item = queue[i]
        if callable(item):
            item = item(messages)
        reply = FakeReply(text=item) if isinstance(item, str) else item
        if reply.error is not None:
            raise reply.error
        parsed: BaseModel | None = None
        text = reply.text
        if response_model is not None:
            try:
                if isinstance(reply.parsed, BaseModel):
                    parsed = reply.parsed
                elif reply.parsed is not None:
                    parsed = response_model.model_validate(reply.parsed)
                else:
                    parsed = response_model.model_validate_json(text)
            except ValidationError as e:
                raise StructuredOutputError(str(e), raw_text=text) from e
            if not text:
                text = parsed.model_dump_json()
        cost = reply.cost if reply.cost is not None else self.default_cost
        return LLMResult(
            text=text,
            tool_calls=list(reply.tool_calls),
            parsed=parsed,
            cost=cost,
            model=f"fake/{role}",
            finish_reason="tool_calls" if reply.tool_calls else "stop",
        )

    def estimate_usd_micros(
        self, role: str, messages: list[Json], *, max_output_tokens: int | None = None
    ) -> int:
        return self.default_cost.usd_micros

    async def embed(self, role: str, texts: list[str]) -> list[list[float]]:
        return HashEmbedder().embed(texts)

    def assert_consumed(self) -> None:
        left = {
            ("*" if k is None else k): len(q) - self._pos[k]
            for k, q in self._queues.items()
            if len(q) > self._pos[k]
        }
        assert not left, f"FakeLLM replies left unconsumed: {left}"
