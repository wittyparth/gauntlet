"""Threat taxonomy (attacks/taxonomy.yaml)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

__all__ = ["DEFAULT_TAXONOMY_PATH", "Category", "Taxonomy", "load_taxonomy"]

DEFAULT_TAXONOMY_PATH = Path(__file__).resolve().parents[5] / "attacks" / "taxonomy.yaml"


@dataclass(frozen=True)
class Category:
    id: str
    number: int
    title: str
    description: str
    owasp_llm: tuple[str, ...]
    owasp_agentic: tuple[str, ...]
    atlas: tuple[str, ...]
    phase_scope: Literal["imported", "own_detectors", "later"]
    dangerous: bool


@dataclass(frozen=True)
class Taxonomy:
    categories: tuple[Category, ...]
    verified_on: str
    sources: Mapping[str, Any] = field(default_factory=dict)

    def get(self, category_id: str) -> Category | None:
        return next((c for c in self.categories if c.id == category_id), None)

    def ids(self) -> list[str]:
        return [c.id for c in self.categories]

    def owasp_index(self) -> dict[str, list[str]]:
        """OWASP LLM id -> category ids (the compliance column of the posture report)."""
        out: dict[str, list[str]] = {}
        for c in self.categories:
            for o in c.owasp_llm:
                out.setdefault(o, []).append(c.id)
        return out


def load_taxonomy(path: Path | None = None) -> Taxonomy:
    data = yaml.safe_load(Path(path or DEFAULT_TAXONOMY_PATH).read_text())
    cats = tuple(
        Category(
            id=c["id"],
            number=int(c["number"]),
            title=c["title"],
            description=c.get("description", ""),
            owasp_llm=tuple(c.get("owasp_llm") or ()),
            owasp_agentic=tuple(c.get("owasp_agentic") or ()),
            atlas=tuple(c.get("atlas") or ()),
            phase_scope=c["phase_scope"],
            dangerous=bool(c["dangerous"]),
        )
        for c in data["categories"]
    )
    return Taxonomy(cats, str(data["verified_on"]), data.get("sources") or {})
