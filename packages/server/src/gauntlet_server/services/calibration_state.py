"""Calibration state to rubric (CQ-R2): the part of calibration that judging and reports need.
No imports from `jobs` or the job handlers, so both can use it."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from gauntlet_core.judges import CalibrationState
from gauntlet_core.judges import effective_rubric as core_effective_rubric
from gauntlet_core.schema import Rubric
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Rubric as RubricRow
from ..db.review_models import Calibration

__all__ = [
    "JUDGE_ROLES",
    "apply_calibration",
    "effective_rubric",
    "judge_models",
    "latest_states",
]

JUDGE_ROLES = ("judge_small", "judge_strong")


def judge_models(roles: Mapping[str, Any] | None) -> dict[str, str]:
    """{judge_small, judge_strong} model ids out of a `{role: model | {model, ...}}` mapping
    (run manifests hold plain ids, `runs.role_settings` holds `{model, reasoning}`)."""
    out: dict[str, str] = {}
    for r in JUDGE_ROLES:
        v = (roles or {}).get(r)
        if isinstance(v, Mapping):
            v = v.get("model")
        if v:
            out[r] = str(v)
    return out


async def latest_states(
    s: AsyncSession,
    ws: str,
    rubrics: Mapping[str, Rubric],
    models: Mapping[str, str] | None,
) -> dict[str, CalibrationState]:
    """The latest finished calibration per rubric id for the rubric's own version. A row is
    stale when flagged so, or when `models` (if given) differ from the models it was run with."""
    if not rubrics:
        return {}
    rows = (
        (
            await s.execute(
                select(Calibration)
                .where(
                    Calibration.workspace_id == ws,
                    Calibration.rubric_id.in_(list(rubrics)),
                    Calibration.status == "done",
                )
                .order_by(Calibration.created_at.desc(), Calibration.id.desc())
            )
        )
        .scalars()
        .all()
    )
    out: dict[str, CalibrationState] = {}
    for c in rows:
        if c.rubric_id in out or c.rubric_version != rubrics[c.rubric_id].version:
            continue
        stale = c.stale or (models is not None and dict(c.judge_models) != dict(models))
        out[c.rubric_id] = CalibrationState(
            c.rubric_version,
            c.threshold if c.threshold is not None else rubrics[c.rubric_id].threshold,
            c.gating_allowed,
            stale,
        )
    return out


async def apply_calibration(
    s: AsyncSession,
    ws: str,
    rubrics: Mapping[str, Rubric],
    models: Mapping[str, str] | None,
) -> dict[str, Rubric]:
    states = await latest_states(s, ws, rubrics, models)
    return {rid: core_effective_rubric(r, states.get(rid)) for rid, r in rubrics.items()}


async def effective_rubric(
    s: AsyncSession,
    ws: str,
    rubric_id: str,
    version: int | None = None,
    *,
    models: Mapping[str, str] | None = None,
) -> Rubric:
    """The rubric document (latest version unless given) with calibrated `threshold` and
    `gating_allowed`, else the document defaults. Library rubrics resolve too."""
    from gauntlet_core.eval import load_rubrics

    q = select(RubricRow).where(RubricRow.workspace_id == ws, RubricRow.id == rubric_id)
    q = q.where(RubricRow.version == version) if version else q.order_by(RubricRow.version.desc())
    row = (await s.execute(q.limit(1))).scalar_one_or_none()
    if row is not None:
        rub = Rubric.model_validate(row.doc)
    else:
        lib = load_rubrics().get(rubric_id)
        if lib is None or (version and lib.version != version):
            raise LookupError(f"rubric {rubric_id} v{version or 'latest'} not found")
        rub = lib
    return (await apply_calibration(s, ws, {rubric_id: rub}, models))[rubric_id]
