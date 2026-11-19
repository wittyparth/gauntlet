"""The rubric library v1 (seven rubrics, shipped as YAML beside this file)."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from gauntlet_core.schema import Rubric, load_yaml

from .rules import RULE_STAGE, commitment_candidates, rule_context

__all__ = ["RULE_STAGE", "commitment_candidates", "load_rubrics", "rule_context"]

_DIR = Path(__file__).parent


def load_rubrics(ids: Iterable[str] | None = None) -> dict[str, Rubric]:
    """All rubrics, or the requested ids (unknown id: KeyError listing the known ones)."""
    available = sorted(p.stem for p in _DIR.glob("*.yaml"))
    wanted = available if ids is None else list(ids)
    missing = [i for i in wanted if i not in available]
    if missing:
        raise KeyError(f"unknown rubric(s) {missing}; available: {available}")
    return {i: load_yaml(Rubric, _DIR / f"{i}.yaml") for i in wanted}
