"""Shared result schema and CLI plumbing for the meta-evaluation studies (P5-5).

Every study is `python -m studies.<name> --seed N [--smoke] --out benchmarks/results/<name>.json`
and writes one `StudyResult`. Smoke configurations use scripted brains, fixtures or cassettes:
no model, no network, no spend. Live full runs are manual and need the lead's go."""

from __future__ import annotations

import argparse
import asyncio
import random
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from gauntlet_core.stats.intervals import percentile, wilson_interval
from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "DATA_DIR",
    "REPO",
    "RESULTS_DIR",
    "StudyResult",
    "bootstrap_mean",
    "load_results",
    "now",
    "platform_version",
    "run_cli",
    "version_tuple",
    "wilson",
    "write_result",
]

REPO = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO / "benchmarks" / "results"
DATA_DIR = Path(__file__).resolve().parent / "data"


def platform_version() -> str:
    try:
        return version("gauntlet-server")
    except PackageNotFoundError:
        return "0.0.0"


def version_tuple(v: str) -> tuple[int, ...]:
    parts: list[int] = []
    for p in v.split("."):
        digits = "".join(c for c in p if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


class StudyResult(BaseModel):
    """Metrics are never rounded; intervals bracket their metric; every metric that has an
    interval renders as an interval, not a point."""

    model_config = ConfigDict(extra="forbid")
    name: str
    version: int = 1
    seed: int
    platform_version: str
    started_at: datetime
    smoke: bool = False
    metrics: dict[str, float]
    intervals: dict[str, tuple[float, float]] = Field(default_factory=dict)
    n: int
    limitations: list[str]
    notes: str = ""

    @model_validator(mode="after")
    def _check(self) -> StudyResult:
        for k, (lo, hi) in self.intervals.items():
            if k not in self.metrics:
                raise ValueError(f"interval for unknown metric {k!r}")
            v = self.metrics[k]
            if not (lo - 1e-9 <= v <= hi + 1e-9):
                raise ValueError(f"interval of {k!r} does not bracket {v}: ({lo}, {hi})")
        if not self.limitations:
            raise ValueError("a study result needs at least one limitation")
        return self


def wilson(successes: int, n: int) -> tuple[float, float]:
    return wilson_interval(successes, n)


def bootstrap_mean(
    values: Sequence[float], *, seed: int, resamples: int = 1000
) -> tuple[float, float, float]:
    """(mean, low, high) with a percentile bootstrap; empty input gives (0, 0, 0)."""
    if not values:
        return (0.0, 0.0, 0.0)
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(rng.choices(values, k=n)) / n for _ in range(resamples))
    mean = sum(values) / n
    return (mean, min(percentile(means, 0.025), mean), max(percentile(means, 0.975), mean))


def load_results(directory: Path | None = None) -> list[StudyResult]:
    d = directory or RESULTS_DIR
    return [StudyResult.model_validate_json(p.read_text()) for p in sorted(d.glob("*.json"))]


def write_result(result: StudyResult, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result.model_dump_json(indent=2) + "\n")


def now() -> datetime:
    return datetime.now(UTC)


def run_cli(
    name: str,
    build: Callable[..., Awaitable[StudyResult]],
    argv: Sequence[str] | None = None,
    *,
    extra: dict[str, type] | None = None,
) -> int:
    """`extra` maps additional `--flag` names (path inputs) to their type; they are passed to
    `build` as keyword arguments."""
    ap = argparse.ArgumentParser(prog=f"studies.{name}")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--out", type=Path, default=RESULTS_DIR / f"{name}.json")
    for flag, typ in (extra or {}).items():
        ap.add_argument(f"--{flag}", type=typ, default=None)
    ns = ap.parse_args(argv)
    kwargs = {flag: getattr(ns, flag) for flag in (extra or {})}
    result = asyncio.run(build(ns.seed, ns.smoke, **kwargs))
    write_result(result, ns.out)
    print(f"{name}: wrote {ns.out}")
    return 0
