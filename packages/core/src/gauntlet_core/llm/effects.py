"""llm_effect: the only way episode code calls a model (CQ-B1). The call is a journaled
effect, so a replay returns the recorded result and makes zero model calls."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from gauntlet_core.engine import EpisodeCtx, PermanentEffectError
from gauntlet_core.schema import Cost, Json

from .gateway import Gateway
from .types import GatewayError, LLMResult, ToolCallRequest


def _dump(r: LLMResult) -> Json:
    return {
        "text": r.text,
        "tool_calls": [
            {"id": t.id, "name": t.name, "arguments": t.arguments} for t in r.tool_calls
        ],
        "parsed": r.parsed.model_dump(mode="json") if r.parsed is not None else None,
        "model": r.model,
        "finish_reason": r.finish_reason,
        "latency_ms": r.latency_ms,
        "cost": r.cost.model_dump(mode="json"),
    }


def _load(d: Json, response_model: type[BaseModel] | None) -> LLMResult:
    parsed = None
    if d.get("parsed") is not None and response_model is not None:
        parsed = response_model.model_validate(d["parsed"])
    return LLMResult(
        text=d["text"],
        tool_calls=[ToolCallRequest(t["id"], t["name"], t["arguments"]) for t in d["tool_calls"]],
        parsed=parsed,
        cost=Cost.model_validate(d["cost"]),
        model=d["model"],
        finish_reason=d["finish_reason"],
        latency_ms=d["latency_ms"],
    )


async def llm_effect(
    ctx: EpisodeCtx,
    gateway: Gateway,
    role: str,
    messages: list[Json],
    *,
    tools: list[Json] | None = None,
    response_model: type[BaseModel] | None = None,
    temperature: float | None = None,
    seed: int | None = None,
    error_cls: type[PermanentEffectError] = PermanentEffectError,
    retry_safe: bool = True,
) -> LLMResult:
    request: Json = {
        "role": role,
        "messages": messages,
        "tools": tools,
        "response_model": response_model.model_json_schema() if response_model else None,
        "temperature": temperature,
        "seed": seed,
    }
    est = 0
    estimator: Any = getattr(gateway, "estimate_usd_micros", None)
    if estimator is not None:
        est = int(estimator(role, messages))

    async def fn() -> tuple[Json, Cost | None]:
        try:
            result = await gateway.complete(
                role,
                messages,
                tools=tools,
                response_model=response_model,
                temperature=temperature,
                seed=seed,
            )
        except GatewayError as e:
            raise error_cls(e.code, e.message) from e
        return _dump(result), result.cost

    recorded = await ctx.effect("llm", request, fn, retry_safe=retry_safe, est_usd_micros=est)
    return _load(recorded, response_model)
