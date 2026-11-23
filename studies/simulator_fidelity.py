"""Simulator fidelity: the guard-rule hit rate and the persona-guard rubric pass rate over a
file of simulator turns `[{text, agent_messages, hidden_facts, language, rubric_pass}]`
(`--turns PATH`; `rubric_pass` is the recorded small-judge verdict). Smoke uses a synthetic
fixture."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from gauntlet_core.judges.simguard import SimulatorGuard

from .common import DATA_DIR, StudyResult, now, platform_version, run_cli, wilson

SMOKE_TURNS = DATA_DIR / "sim_turns_smoke.json"


async def build(seed: int, smoke: bool, turns: Path | None = None) -> StudyResult:
    path = turns or (SMOKE_TURNS if smoke else None)
    if path is None:
        raise SystemExit("simulator_fidelity needs --turns PATH or --smoke")
    rows = json.loads(path.read_text())
    hits = passes = 0
    for r in rows:
        guard = SimulatorGuard(
            hidden_facts=r.get("hidden_facts", []), persona_language=r.get("language")
        )
        if guard.check(r["text"], r.get("agent_messages", [])) is not None:
            hits += 1
        if r.get("rubric_pass"):
            passes += 1
    n = len(rows)
    return StudyResult(
        name="simulator_fidelity", seed=seed, platform_version=platform_version(),
        started_at=now(), smoke=smoke,
        metrics={
            "guard_rule_hit_rate": hits / n if n else 0.0,
            "persona_rubric_pass_rate": passes / n if n else 0.0,
        },
        intervals={
            "guard_rule_hit_rate": wilson(hits, n),
            "persona_rubric_pass_rate": wilson(passes, n),
        },
        n=n,
        limitations=[
            "A low hit rate means few detected breaches of character, not proof of fidelity.",
            "The rubric verdicts are recorded outputs of a small judge, not human ratings.",
            *(["SMOKE: synthetic turns."] if smoke else []),
        ],
    )  # fmt: skip


if __name__ == "__main__":
    sys.exit(run_cli("simulator_fidelity", build, extra={"turns": Path}))
