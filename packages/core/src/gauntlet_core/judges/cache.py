"""Judge call cache. It sits at the gateway boundary so journaled effect ordinals never
depend on cache state: an episode's `llm` effect always exists, only the model call inside it
may be skipped. The key is sha256 over the role (which fixes the model), its reasoning
setting, the full rendered messages (rubric version, definitions and trajectory) and the
output schema."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Protocol

from pydantic import BaseModel

from gauntlet_core.llm import LLMResult
from gauntlet_core.llm.gateway import Gateway
from gauntlet_core.schema import Cost, Json


class JudgeCache(Protocol):
    def get(self, key: str) -> LLMResult | None: ...

    def put(self, key: str, value: LLMResult) -> None: ...


class MemoryJudgeCache:
    def __init__(self) -> None:
        self._d: dict[str, LLMResult] = {}
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> LLMResult | None:
        v = self._d.get(key)
        if v is None:
            self.misses += 1
        else:
            self.hits += 1
        return v

    def put(self, key: str, value: LLMResult) -> None:
        self._d[key] = value


def cache_key(
    role: str,
    messages: list[Json],
    response_model: type[BaseModel] | None,
    temperature: float | None,
    reasoning: str = "default",
) -> str:
    payload = {
        "role": role,
        "messages": messages,
        "schema": response_model.model_json_schema() if response_model else None,
        "temperature": temperature,
        "reasoning": reasoning,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


class CachingGateway:
    def __init__(self, inner: Gateway, cache: JudgeCache) -> None:
        self.inner, self.cache = inner, cache

    def _reasoning(self, role: str) -> str:
        roles = getattr(getattr(getattr(self.inner, "config", None), "llm", None), "roles", {})
        rc = roles.get(role)
        return rc.reasoning if rc is not None else "default"

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
        if tools:  # only plain judge calls are cached
            return await self.inner.complete(
                role,
                messages,
                tools=tools,
                response_model=response_model,
                temperature=temperature,
                seed=seed,
                max_output_scale=max_output_scale,
            )
        key = cache_key(role, messages, response_model, temperature, self._reasoning(role))
        hit = self.cache.get(key)
        if hit is not None:
            return dataclasses.replace(hit, cost=Cost(), latency_ms=0)
        res = await self.inner.complete(
            role,
            messages,
            tools=tools,
            response_model=response_model,
            temperature=temperature,
            seed=seed,
            max_output_scale=max_output_scale,
        )
        self.cache.put(key, res)
        return res

    def estimate_usd_micros(
        self, role: str, messages: list[Json], *, max_output_tokens: int | None = None
    ) -> int:
        return self.inner.estimate_usd_micros(role, messages, max_output_tokens=max_output_tokens)

    async def embed(self, role: str, texts: list[str]) -> list[list[float]]:
        return await self.inner.embed(role, texts)
