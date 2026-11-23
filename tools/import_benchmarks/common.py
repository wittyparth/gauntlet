"""Shared importer plumbing: pins, reports, replaying ground-truth actions through handlers and
turning the resulting state change into `state` checks."""

from __future__ import annotations

import importlib
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from gauntlet_core.schema import WorldSpec
from gauntlet_core.world import WorldState, WorldView

__all__ = [
    "ImportReport",
    "PinError",
    "Reason",
    "load_handler",
    "replay",
    "require_pin",
    "state_checks",
    "write_yaml",
]

CLOCK = datetime(2026, 3, 15, 10, tzinfo=UTC)


class PinError(SystemExit):
    """The pin does not equal the recorded upstream commit."""


@dataclass(frozen=True)
class Reason:
    item: str
    reason: str


@dataclass
class ImportReport:
    tasks: int = 0
    portable: int = 0
    skipped: list[Reason] = field(default_factory=list)
    licence: str = "MIT"
    pin: str = ""

    @property
    def portable_pct(self) -> float:
        return round(100.0 * self.portable / self.tasks, 1) if self.tasks else 0.0

    def summary(self) -> str:
        by: dict[str, int] = {}
        for s in self.skipped:
            key = s.reason.split(":")[0]
            by[key] = by.get(key, 0) + 1
        why = ", ".join(f"{k} {v}" for k, v in sorted(by.items())) or "none"
        return f"{self.portable}/{self.tasks} portable ({self.portable_pct}%); skipped: {why}"


def require_pin(pin: str, recorded: str, *, allow_unpinned: bool = False) -> None:
    """Importers refuse to run unless `pin` equals the recorded upstream commit or version."""
    if pin == recorded:
        return
    if not allow_unpinned:
        raise PinError(
            f"refusing to import: --pin {pin!r} is not the recorded upstream pin {recorded!r}. "
            "Pass --allow-unpinned to override (the result is then not reproducible)."
        )
    print(f"WARNING: importing unpinned source {pin!r} (recorded {recorded!r})", file=sys.stderr)


def write_yaml(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))


def load_handler(entrypoint: str) -> Any:
    mod, _, fn = entrypoint.partition(":")
    return getattr(importlib.import_module(mod), fn)


def replay(
    world: WorldSpec, calls: list[tuple[str, dict[str, Any]]]
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], list[str]]:
    """Run `calls` through the world's python handlers from the seed. Returns (before, after,
    errors); `errors` lists calls that failed or named an unknown tool."""
    state = WorldState.from_seed(world.seed)
    before = json.loads(json.dumps(state.snapshot(), default=str))
    tools = {t.name: t for t in world.tools}
    errors: list[str] = []
    for name, args in calls:
        spec = tools.get(name)
        if spec is None or spec.handler.kind != "python":
            errors.append(f"unknown_tool:{name}")
            continue
        out = load_handler(spec.handler.entrypoint)(WorldView(state), dict(args), CLOCK)
        if out.error:
            errors.append(f"{name}:{out.error}")
            continue
        state.apply(out.patch)
    after = json.loads(json.dumps(state.snapshot(), default=str))
    return before, after, errors


def state_checks(
    before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """One `state` check per changed top-level field of every changed or added record."""
    checks: list[dict[str, Any]] = []
    for coll in sorted(after):
        for rid, rec in sorted(after[coll].items()):
            old = before.get(coll, {}).get(rid)
            if old == rec:
                continue
            for key in sorted(rec):
                if old is None or old.get(key) != rec[key]:
                    node: dict[str, Any] = {"type": "state", "collection": coll}
                    if old is None:  # created by the actions: not in the seed, so select by field
                        node["where"] = {"id": {"eq": rid}}
                    else:
                        node["id"] = rid
                    checks.append({**node, "path": key, "matcher": {"eq": rec[key]}})
    return checks
