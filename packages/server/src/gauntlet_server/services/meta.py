"""Public benchmark data (P5-5): the committed study result files, served read-only.

No workspace data is involved: the files live in the repository (`benchmarks/results`) or the
directory named by `GAUNTLET_BENCHMARKS_DIR`. Invalid files are skipped and logged, never
served."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

__all__ = ["BenchmarksOut", "StudyOut", "load_benchmarks"]

log = logging.getLogger("gauntlet.meta")
DEFAULT_DIR = "benchmarks/results"


class StudyOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    version: int
    seed: int
    platform_version: str
    started_at: datetime
    smoke: bool = False
    metrics: dict[str, float]
    intervals: dict[str, tuple[float, float]] = Field(default_factory=dict)
    n: int
    limitations: list[str]
    notes: str = ""


class BenchmarksOut(BaseModel):
    studies: list[StudyOut]


_cache: dict[str, tuple[tuple[tuple[str, float], ...], BenchmarksOut]] = {}


def load_benchmarks(directory: str = "") -> BenchmarksOut:
    d = Path(directory or DEFAULT_DIR)
    files = sorted(d.glob("*.json")) if d.is_dir() else []
    stamp = tuple((p.name, p.stat().st_mtime) for p in files)
    hit = _cache.get(str(d))
    if hit is not None and hit[0] == stamp:
        return hit[1]
    studies: list[StudyOut] = []
    for p in files:
        try:
            studies.append(StudyOut.model_validate(json.loads(p.read_text())))
        except (ValueError, ValidationError, OSError):
            log.warning("skipping invalid study result %s", p.name)
    out = BenchmarksOut(studies=studies)
    _cache[str(d)] = (stamp, out)
    return out
