"""Naming a cluster from its exemplars with the `generator` role (P3-6)."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from gauntlet_core.llm.gateway import Gateway
from gauntlet_core.schema import Json

__all__ = ["ClusterName", "Exemplar", "MemoryNameCache", "NameCache", "name_cluster"]

ROLE = "generator"
SYSTEM = (
    "You name groups of failed episodes from an AI agent evaluation. Given examples of one "
    "group, answer with a short name (at most 6 words), a description (at most 30 words) and "
    "one sentence on the suspected cause. Use only what the examples say."
)


class ClusterName(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(max_length=80)
    description: str = Field(max_length=300)
    suspected_cause: str = Field(max_length=300)


@dataclass(frozen=True)
class Exemplar:
    episode_id: str
    text: str


class NameCache(Protocol):
    def get(self, key: str) -> ClusterName | None: ...
    def put(self, key: str, value: ClusterName) -> None: ...


class MemoryNameCache:
    def __init__(self) -> None:
        self._d: dict[str, ClusterName] = {}

    def get(self, key: str) -> ClusterName | None:
        return self._d.get(key)

    def put(self, key: str, value: ClusterName) -> None:
        self._d[key] = value


def cache_key(member_ids: Sequence[str], model: str) -> str:
    return hashlib.sha256(("|".join(sorted(member_ids)) + "#" + model).encode()).hexdigest()


def _fit(n: ClusterName) -> ClusterName:
    words = n.name.split()
    return ClusterName(
        name=" ".join(words[:6]),
        description=" ".join(n.description.split()[:30]),
        suspected_cause=n.suspected_cause,
    )


async def name_cluster(
    exemplars: Sequence[Exemplar],
    gateway: Gateway,
    *,
    fallback: str,
    member_ids: Sequence[str] = (),
    model: str = ROLE,
    cache: NameCache | None = None,
) -> ClusterName:
    """Cached by `sha256(sorted member ids + model)`. A failed call returns `fallback` as the
    name (callers pass `"Cluster {label}: {most common failed check id}"`)."""
    key = cache_key(member_ids or [e.episode_id for e in exemplars], model)
    if cache is not None and (hit := cache.get(key)) is not None:
        return hit
    examples = "\n".join(f"{i}. {e.text}" for i, e in enumerate(exemplars[:6], 1))
    messages: list[Json] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Examples of one group of failures:\n{examples}"},
    ]
    try:
        res = await gateway.complete(ROLE, messages, response_model=ClusterName, temperature=0.0)
        if not isinstance(res.parsed, ClusterName):
            raise ValueError("no structured output")
        out = _fit(res.parsed)
    except Exception:
        return ClusterName(name=fallback, description="", suspected_cause="")
    if cache is not None:
        cache.put(key, out)
    return out
