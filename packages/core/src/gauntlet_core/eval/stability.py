"""Flaky detection, quarantine suggestions, and the adaptive-sampling decision (P3-2)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from gauntlet_core.stats import sequential_decision

__all__ = [
    "Flaky",
    "QuarantineSuggestion",
    "ScenarioRunSummary",
    "adaptive_decision",
    "classify_flaky",
    "initial_repetitions",
    "suggest_quarantine",
]

MIN_FLAKY_TRIALS = 3
FLAKY_RUNS, FLAKY_WINDOW = 3, 5
SIM_ERROR_SHARE, SIM_WINDOW = 0.3, 10
ADAPTIVE_START = 3
ADAPTIVE_EXTRA = 2  # hard cap: repetitions + 2 episodes per scenario, excluded ones included


@dataclass(frozen=True)
class Flaky:
    flaky: bool
    flakiness: float | None  # 1 - |2 * rate - 1|; 1.0 is a coin flip


def classify_flaky(trials: Sequence[bool]) -> Flaky:
    n, passed = len(trials), sum(1 for t in trials if t)
    if n < MIN_FLAKY_TRIALS:
        return Flaky(False, None)
    rate = passed / n
    return Flaky(0 < passed < n, 1 - abs(2 * rate - 1))


@dataclass(frozen=True)
class ScenarioRunSummary:
    """One scenario in one completed run of one agent version."""

    run_id: str
    flaky: bool
    outcomes: tuple[str, ...]  # every episode outcome of the scenario in that run, in order


@dataclass(frozen=True)
class QuarantineSuggestion:
    kind: Literal["flaky", "simulator_errors"]
    reason: str


def suggest_quarantine(history: Sequence[ScenarioRunSummary]) -> QuarantineSuggestion | None:
    """`history` is newest first. Flaky in at least 3 of the last 5 runs, or simulator errors
    in at least 30 percent of the last 10 episodes."""
    recent = history[:FLAKY_WINDOW]
    flaky_runs = sum(1 for h in recent if h.flaky)
    if flaky_runs >= FLAKY_RUNS:
        return QuarantineSuggestion(
            "flaky", f"flaky in {flaky_runs} of the last {len(recent)} runs of this agent version"
        )
    episodes = [o for h in reversed(history) for o in h.outcomes][-SIM_WINDOW:]
    errors = sum(1 for o in episodes if o == "simulator_error")
    if len(episodes) >= SIM_WINDOW and errors / len(episodes) >= SIM_ERROR_SHARE:
        return QuarantineSuggestion(
            "simulator_errors", f"simulator errors in {errors} of the last {len(episodes)} episodes"
        )
    return None


def initial_repetitions(repetitions: int) -> int:
    """Episodes created up front for an adaptive scenario."""
    return min(ADAPTIVE_START, repetitions)


def adaptive_decision(
    *, passed: int, counted: int, excluded: int, repetitions: int
) -> Literal["continue", "stop"]:
    """One more repetition for this scenario? Beta(1, 1) sequential rule over the counted
    trials (L4); excluded outcomes are not trials but count toward the hard episode cap."""
    if counted + excluded >= repetitions + ADAPTIVE_EXTRA:
        return "stop"
    decision = sequential_decision(passed, counted, max_trials=repetitions).decision
    return "continue" if decision == "continue" else "stop"


class AdaptiveScheduler:
    """The in-memory twin of the server's `adaptive_step` (local CLI runs): at most one extra
    repetition per scenario in flight, decided only once the scenario has nothing in flight."""

    def __init__(self, repetitions: int) -> None:
        self.repetitions = repetitions
        self._created: dict[str, int] = {}
        self._finished: dict[str, int] = {}
        self._passed: dict[str, int] = {}
        self._counted: dict[str, int] = {}
        self._excluded: dict[str, int] = {}

    def start(self, scenario_ids: Sequence[str]) -> dict[str, int]:
        """Initial repetition count per scenario."""
        n = initial_repetitions(self.repetitions)
        for sid in scenario_ids:
            self._created[sid] = n
        return dict.fromkeys(scenario_ids, n)

    def record(self, scenario_id: str, outcome: str) -> int | None:
        """An episode finished. Returns the `rep` number of one new episode to run, or None."""
        sid = scenario_id
        self._finished[sid] = self._finished.get(sid, 0) + 1
        if outcome in ("passed", "failed"):
            self._counted[sid] = self._counted.get(sid, 0) + 1
            self._passed[sid] = self._passed.get(sid, 0) + (outcome == "passed")
        else:
            self._excluded[sid] = self._excluded.get(sid, 0) + 1
        if self._finished[sid] < self._created.get(sid, 0):
            return None  # something of this scenario is still in flight
        decision = adaptive_decision(
            passed=self._passed.get(sid, 0),
            counted=self._counted.get(sid, 0),
            excluded=self._excluded.get(sid, 0),
            repetitions=self.repetitions,
        )
        if decision == "stop":
            return None
        rep = self._created[sid]
        self._created[sid] = rep + 1
        return rep
