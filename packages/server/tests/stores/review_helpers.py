"""Shared builders for the review tests."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from pg_helpers import add_run
from sqlalchemy import text

HARD = {
    "id": "rb_hard",
    "version": 1,
    "title": "Hard rule",
    "question": "Did the agent break the hard rule?",
    "pass_definition": "It did not.",
    "fail_definition": "It did.",
    "severity": "low",
    "hard_fail": True,
}


async def add_verdict(
    sm,
    ep: str,
    criterion: str,
    result: str,
    *,
    confidence: float = 0.95,
    stage: str = "small",
    small_result: str | None = None,
    n: int = 0,
) -> None:
    doc: dict[str, Any] = {
        "evaluator": f"judge:{criterion}",
        "rubric_version": 1,
        "criterion": criterion,
        "result": result,
        "severity": "low",
        "hard_fail": False,
        "confidence": confidence,
        "evidence": [],
        "reasoning": "",
        "stage": stage,
        "small_result": small_result,
    }
    async with sm() as s, s.begin():
        await s.execute(
            text(
                "INSERT INTO verdicts (id, workspace_id, episode_id, evaluator, criterion, "
                "result, doc) VALUES (:id, 'ws_test', :e, :ev, :c, :r, CAST(:d AS jsonb))"
            ),
            {"id": f"vrd_{ep}_{criterion}_{n}", "e": ep, "ev": f"judge:{criterion}", "c": criterion,
             "r": result, "d": json.dumps(doc)},
        )  # fmt: skip


async def synthetic_run(
    sm,
    criterion: str,
    spec: Sequence[tuple[str, str, float, str | None, str]],
    run_id: str = "run_syn",
) -> list[str]:
    """spec rows: (scenario, result, confidence, small_result, stage). Returns episode ids."""
    await add_run(sm, run_id, status="done")
    ids = []
    for i, (scn, result, conf, small, stage) in enumerate(spec):
        ep = f"ep_syn_{i:03d}"
        async with sm() as s, s.begin():
            await s.execute(
                text(
                    "INSERT INTO episodes (id, workspace_id, run_id, scenario_id, status, outcome) "
                    "VALUES (:id, 'ws_test', :r, :s, 'done', 'passed')"
                ),
                {"id": ep, "r": run_id, "s": scn},
            )
        await add_verdict(
            sm, ep, criterion, result, confidence=conf, small_result=small, stage=stage
        )
        ids.append(ep)
    return ids
