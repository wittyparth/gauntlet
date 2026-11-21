"""The text that represents one failed episode when clustering (P3-6)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from gauntlet_core.schema import Trajectory, Verdict

__all__ = ["MAX_CHARS", "failed_check_ids", "failure_text"]

MAX_CHARS = 1500
QUOTE_CHARS = 200
MAX_CRITERIA = 3


def failed_check_ids(check_results: Sequence[Mapping[str, object]]) -> list[str]:
    """Ids of the checks that failed the episode: `success` not holding, a forbidden check
    holding. Order of the journal."""
    return [
        str(c["check_id"])
        for c in check_results
        if bool(c["holds"]) != (c["check_id"] == "success")
    ]


def _termination(traj: Trajectory) -> str:
    for e in reversed(traj.events):
        if e.kind == "episode_ended":
            return str(e.payload.get("termination") or "none")
    return "none"


def failure_text(
    trajectory: Trajectory,
    verdicts: Sequence[Verdict],
    check_results: Sequence[Mapping[str, object]],
    outcome: str,
) -> str:
    """`scenario title | failed check ids | up to 3 failed criteria each with its first
    evidence quote | tool names in order | termination`, at most `MAX_CHARS` characters."""
    checks = ",".join(sorted(set(failed_check_ids(check_results)))) or "none"
    crit = []
    for v in [v for v in verdicts if v.result == "fail"][:MAX_CRITERIA]:
        quote = next((e.quote for e in v.evidence if e.quote), "")
        crit.append(f"{v.criterion}: {quote[:QUOTE_CHARS]}" if quote else v.criterion)
    tools = [c.tool for c in trajectory.tool_calls()]
    parts = [
        trajectory.scenario.title,
        f"failed checks: {checks}",
        "failed criteria: " + ("; ".join(crit) if crit else "none"),
        "tools: " + (", ".join(tools) if tools else "none"),
        f"termination: {_termination(trajectory)} ({outcome})",
    ]
    return " | ".join(parts)[:MAX_CHARS]
