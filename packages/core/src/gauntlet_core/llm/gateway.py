"""The Gateway protocol (contracts section 3 plus CQ-B1 additions)."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from gauntlet_core.schema import Json

from .types import LLMResult


class Gateway(Protocol):
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
    ) -> LLMResult: ...

    def estimate_usd_micros(
        self, role: str, messages: list[Json], *, max_output_tokens: int | None = None
    ) -> int: ...

    async def embed(self, role: str, texts: list[str]) -> list[list[float]]: ...
