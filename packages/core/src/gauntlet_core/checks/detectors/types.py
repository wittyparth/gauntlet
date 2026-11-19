"""Shared detector types."""

from __future__ import annotations

from dataclasses import dataclass

QUOTE_MAX = 80


@dataclass(frozen=True)
class Hit:
    label: str
    quote: str
    seq: int | None = None
    start: int | None = None
    end: int | None = None


def clip(s: str) -> str:
    return s if len(s) <= QUOTE_MAX else s[:QUOTE_MAX]
