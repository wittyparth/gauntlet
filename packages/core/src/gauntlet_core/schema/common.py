"""Shared primitives for all schema modules. Imports nothing from the rest of gauntlet_core."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_serializer

Json = dict[str, Any]
Severity = Literal["low", "medium", "high", "critical"]
SEVERITY_ORDER: dict[str, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class Model(BaseModel):
    """Base for every contract model: immutable, unknown fields rejected."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    @model_serializer(mode="wrap")
    def _keep_discriminator(self, handler: Any) -> Any:
        """Discriminator tags have defaults; keep them even under exclude_defaults."""
        data = handler(self)
        if isinstance(data, dict):
            for tag in ("type", "kind"):
                if tag in type(self).model_fields and tag not in data:
                    data = {tag: getattr(self, tag), **data}
        return data


class Cost(Model):
    usd_micros: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    model: str | None = None

    def __add__(self, other: Cost) -> Cost:
        return Cost(
            usd_micros=self.usd_micros + other.usd_micros,
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            model=self.model or other.model,
        )


class Evidence(Model):
    seq: int
    quote: str | None = None
    note: str | None = None
