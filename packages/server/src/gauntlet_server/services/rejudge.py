"""Rejudge one episode (P3-3): run the judge cascade again over the stored trajectory and
replace the verdict rows for that evaluator set. The journal is never touched."""

from __future__ import annotations

from typing import Any

from gauntlet_core.eval import load_rubrics
from gauntlet_core.ids import new_id
from gauntlet_core.llm.types import LLMResult
from gauntlet_core.replay import apply_outcome_rule, rejudge_episode
from gauntlet_core.schema import SCORED_OUTCOMES, Rubric, Verdict
from gauntlet_core.world import build_trajectory, build_world
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Episode, Run
from ..db.models import Rubric as RubricRow
from ..deps import AppState
from ..errors import ApiError, not_found
from ..jobs import load_episode_inputs
from ..models_gateway import gateway_for_roles
from .audit import audit
from .calibration_state import apply_calibration, judge_models
from .reports import _events, apply_human_override

__all__ = ["RejudgeIn", "RejudgeOut", "rejudge"]

TIMEOUT_S = 120


class RejudgeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rubrics: list[str] | None = None
    force: bool = False


class RejudgeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episode_id: str
    rubrics: list[str]
    outcome_before: str | None
    outcome_after: str | None
    verdicts: list[Verdict]
    cost_usd_micros: int


async def _rubrics(s: AsyncSession, ws: str, ids: list[str]) -> list[Rubric]:
    library = load_rubrics()
    out: list[Rubric] = []
    for rid in ids:
        row = (
            await s.execute(
                select(RubricRow)
                .where(RubricRow.workspace_id == ws, RubricRow.id == rid)
                .order_by(RubricRow.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is not None:
            out.append(Rubric.model_validate(row.doc))
        elif rid in library:
            out.append(library[rid])
        else:
            raise not_found("rubric", rid)
    return out


class _Metered:
    """Gateway view that sums what the rejudge spends (also covers cache misses only)."""

    def __init__(self, inner: Any) -> None:
        self.inner, self.usd = inner, 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    async def complete(self, *args: Any, **kw: Any) -> LLMResult:
        res: LLMResult = await self.inner.complete(*args, **kw)
        self.usd += res.cost.usd_micros
        return res


async def rejudge(
    state: AppState, s: AsyncSession, ws: str, episode_id: str, body: RejudgeIn, actor: str
) -> RejudgeOut:
    ep = await s.get(Episode, episode_id)
    if ep is None or ep.workspace_id != ws:
        raise not_found("episode", episode_id)
    if ep.status != "done":
        raise ApiError(409, "episode_not_done", "only a finished episode can be rejudged")
    run = await s.get(Run, ep.run_id)
    assert run is not None
    if run.budget_usd_micros - run.spent_usd_micros - run.reserved_usd_micros <= 0:
        raise ApiError(402, "budget_too_low", "the run has no remaining budget for a rejudge")
    inputs = await load_episode_inputs(s, episode_id)
    ids = body.rubrics if body.rubrics is not None else list(inputs.scenario.rubrics)
    by_id = await apply_calibration(
        s, ws, {r.id: r for r in await _rubrics(s, ws, ids)}, judge_models(run.role_settings)
    )
    rubrics = [by_id[i] for i in ids]
    events = await _events(s, episode_id)
    built = build_world(inputs.world, inputs.scenario.world_overrides, int(ep.rng_seed))
    traj = build_trajectory(episode_id, inputs.scenario, events, built)
    gateway = _Metered(gateway_for_roles(state.gateway, run.role_settings))
    verdicts = await rejudge_episode(
        traj,
        rubrics,
        gateway,  # type: ignore[arg-type]
        policy_text=inputs.manifest.agent_version.profile.policies_text,
        cache=None if body.force else state.judge_cache,
    )
    evaluators = {v.evaluator for v in verdicts} | {f"judge:{r.id}" for r in rubrics}
    await s.execute(
        text(
            "DELETE FROM verdicts WHERE episode_id = :e AND evaluator = ANY(:ev) "
            "AND coalesce(doc->>'stage', '') <> 'human'"
        ),
        {"e": episode_id, "ev": sorted(evaluators)},
    )
    for v in verdicts:
        s.add(_row(ws, episode_id, v))
    await s.flush()
    outcome_before = ep.outcome
    outcome_after = outcome_before
    if outcome_before in SCORED_OUTCOMES:
        rows = (
            await s.execute(
                text("SELECT doc FROM verdicts WHERE episode_id = :e"), {"e": episode_id}
            )
        ).scalars()
        current = apply_human_override([Verdict.model_validate(d) for d in rows])
        checks = [
            (str(e.payload["check_id"]), bool(e.payload["holds"]))
            for e in events
            if e.kind == "check_result"
        ]
        outcome_after = apply_outcome_rule(checks, current)
        ep.outcome = outcome_after
    await s.execute(
        text("UPDATE runs SET spent_usd_micros = spent_usd_micros + :c WHERE id = :r"),
        {"c": gateway.usd, "r": run.id},
    )
    await audit(
        s, ws, actor, "episode.rejudged", "episode", episode_id,
        {"rubrics": ids, "force": body.force, "cost_usd_micros": gateway.usd,
         "outcome_history": [outcome_before, outcome_after]},
    )  # fmt: skip
    await s.commit()
    return RejudgeOut(
        episode_id=episode_id,
        rubrics=ids,
        outcome_before=outcome_before,
        outcome_after=outcome_after,
        verdicts=verdicts,
        cost_usd_micros=gateway.usd,
    )


def _row(ws: str, episode_id: str, v: Verdict) -> Any:
    from ..db.models import Verdict as VerdictRow

    return VerdictRow(
        id=new_id("vrd"),
        workspace_id=ws,
        episode_id=episode_id,
        evaluator=v.evaluator,
        criterion=v.criterion,
        result=v.result,
        doc=v.model_dump(mode="json"),
    )
