"""Live-mode plumbing for the recall script: a hard dollar cap around the LLM gateway and an
adapter that lets the DVA brain call models through that gateway (reasoning off, priced,
capped) instead of calling litellm directly."""

from __future__ import annotations

import json
from types import SimpleNamespace as NS
from typing import Any

from gauntlet_core.llm import Gateway, GatewayError, LLMResult
from gauntlet_core.schema import Json

__all__ = ["TARGET_ROLE", "BudgetExceeded", "CappedGateway", "gateway_complete"]

TARGET_ROLE = "dva_target"


class BudgetExceeded(GatewayError):
    """The next model call could push spend over the cap. Not retryable."""

    code = "budget_exceeded"
    retryable = False


class CappedGateway:
    """Wraps a Gateway. Before each call it checks `spent + estimate <= cap`; after, it adds the
    actual cost. Once a call is refused the gateway stays tripped: every later call is refused
    too, so a half-finished episode cannot keep spending."""

    def __init__(self, inner: Gateway, cap_usd_micros: int) -> None:
        self.inner, self.cap, self.spent = inner, cap_usd_micros, 0
        self.tripped = False
        self.by_model: dict[str, int] = {}

    async def complete(self, role: str, messages: list[Json], **kw: Any) -> LLMResult:
        est = self.inner.estimate_usd_micros(role, messages)
        if self.tripped or self.spent + est > self.cap:
            self.tripped = True
            raise BudgetExceeded(
                f"cap {self.cap} micros: spent {self.spent}, next call estimated {est}"
            )
        res = await self.inner.complete(role, messages, **kw)
        self.spent += res.cost.usd_micros
        self.by_model[res.model] = self.by_model.get(res.model, 0) + res.cost.usd_micros
        return res

    def estimate_usd_micros(
        self, role: str, messages: list[Json], *, max_output_tokens: int | None = None
    ) -> int:
        return self.inner.estimate_usd_micros(role, messages, max_output_tokens=max_output_tokens)

    async def embed(self, role: str, texts: list[str]) -> list[list[float]]:
        return await self.inner.embed(role, texts)


def gateway_complete(gateway: Gateway, role: str = TARGET_ROLE) -> Any:
    """A `brain_llm` completion function backed by `gateway.complete(role, ...)`."""

    async def complete(*, model: str, messages: list[Any], tools: Any = None, **kw: Any) -> Any:
        res = await gateway.complete(role, messages, tools=tools, temperature=kw.get("temperature"))
        calls = [
            NS(id=c.id, function=NS(name=c.name, arguments=json.dumps(c.arguments)))
            for c in res.tool_calls
        ]
        return NS(choices=[NS(message=NS(content=res.text, tool_calls=calls))])

    return complete
