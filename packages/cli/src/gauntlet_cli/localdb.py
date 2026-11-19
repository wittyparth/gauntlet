"""Local run metadata, SQLite beside the journal (`<run dir>/local.db`). Verdicts are not
stored here: they are read from the journal's `verdict` events."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

__all__ = ["LocalDb", "LocalEpisode"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS local_runs (
    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, manifest TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS local_episodes (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, scenario_id TEXT NOT NULL, rep INTEGER NOT NULL,
    outcome TEXT, termination TEXT, cost_usd_micros INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0, reasons TEXT NOT NULL DEFAULT '[]',
    world_fidelity TEXT NOT NULL DEFAULT 'full');
"""


@dataclass(frozen=True)
class LocalEpisode:
    id: str
    run_id: str
    scenario_id: str
    rep: int
    outcome: str | None
    termination: str | None
    cost_usd_micros: int
    latency_ms: int
    reasons: tuple[str, ...]
    world_fidelity: str


class LocalDb:
    def __init__(self, path: Path) -> None:
        self._c = sqlite3.connect(path)
        self._c.executescript(_SCHEMA)

    def close(self) -> None:
        self._c.close()

    def add_run(self, run_id: str, created_at: str, manifest_json: str, status: str) -> None:
        with self._c:
            self._c.execute(
                "INSERT OR IGNORE INTO local_runs VALUES (?, ?, ?, ?)",
                (run_id, created_at, manifest_json, status),
            )

    def set_status(self, run_id: str, status: str) -> None:
        with self._c:
            self._c.execute("UPDATE local_runs SET status = ? WHERE id = ?", (status, run_id))

    def status(self, run_id: str) -> str | None:
        row = self._c.execute("SELECT status FROM local_runs WHERE id = ?", (run_id,)).fetchone()
        return row[0] if row else None

    def add_episode(self, ep_id: str, run_id: str, scenario_id: str, rep: int) -> None:
        with self._c:
            self._c.execute(
                "INSERT OR IGNORE INTO local_episodes (id, run_id, scenario_id, rep) "
                "VALUES (?, ?, ?, ?)",
                (ep_id, run_id, scenario_id, rep),
            )

    def finish_episode(
        self,
        ep_id: str,
        outcome: str,
        termination: str | None,
        cost_usd_micros: int,
        latency_ms: int,
        reasons: tuple[str, ...],
        world_fidelity: str,
    ) -> None:
        with self._c:
            self._c.execute(
                "UPDATE local_episodes SET outcome=?, termination=?, cost_usd_micros=?, "
                "latency_ms=?, reasons=?, world_fidelity=? WHERE id=?",
                (
                    outcome,
                    termination,
                    cost_usd_micros,
                    latency_ms,
                    json.dumps(list(reasons)),
                    world_fidelity,
                    ep_id,
                ),
            )

    def episodes(self, run_id: str) -> list[LocalEpisode]:
        rows = self._c.execute(
            "SELECT id, run_id, scenario_id, rep, outcome, termination, cost_usd_micros, "
            "latency_ms, reasons, world_fidelity FROM local_episodes WHERE run_id = ? "
            "ORDER BY scenario_id, rep",
            (run_id,),
        ).fetchall()
        return [
            LocalEpisode(
                r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], tuple(json.loads(r[8])), r[9]
            )
            for r in rows
        ]
