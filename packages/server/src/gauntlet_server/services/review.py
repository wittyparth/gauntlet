"""Human review queue and labels (P3-5, CQ-R6).

The queue is blind: items never carry judge verdicts. A label is a `verdicts` row with
`stage="human"` that overrides the judge verdicts of its criterion in reports; the episode
outcome is recomputed from the rows, the journal is never modified."""

from __future__ import annotations

import hashlib
import random
from collections import Counter
from datetime import UTC, datetime
from typing import Any, Literal

from gauntlet_core.eval import load_rubrics
from gauntlet_core.ids import new_id
from gauntlet_core.judges import render_trajectory
from gauntlet_core.replay import apply_outcome_rule
from gauntlet_core.schema import SCORED_OUTCOMES, Rubric, Verdict
from gauntlet_core.world import build_trajectory, build_world
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Episode
from ..db.models import Rubric as RubricRow
from ..db.models import Verdict as VerdictRow
from ..db.review_models import HumanLabel
from ..errors import ApiError, not_found
from ..jobs import load_episode_inputs
from .audit import audit
from .reports import _events, apply_human_override

__all__ = [
    "ItemOut",
    "LabelIn",
    "LabelOut",
    "QueueItem",
    "QueueOut",
    "get_item",
    "put_label",
    "review_queue",
]

UNCERTAIN = (0.4, 0.8)
RANDOM_SHARE = 0.10
PER_SCENARIO = 3
Reason = Literal["disagreement", "uncertain", "random"]


class QueueItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episode_id: str
    rubric_id: str
    rubric_version: int | None
    scenario_id: str
    reason: Reason


class QueueOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rubric_id: str
    labeler: str
    items: list[QueueItem]


class LabelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episode_id: str
    rubric_id: str
    result: Literal["pass", "fail", "na"]
    note: str | None = None


class LabelOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    episode_id: str
    rubric_id: str
    rubric_version: int | None
    result: str
    labeler: str
    note: str | None
    is_golden: bool
    outcome_before: str | None
    outcome_after: str | None


class ItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episode_id: str
    rubric: Rubric
    scenario_id: str
    scenario_title: str
    goal: str
    transcript: str
    my_label: str | None
    judge: Verdict | None = None  # only with reveal=true after the caller labelled the item


async def _rubric_doc(s: AsyncSession, ws: str, rubric_id: str, version: int | None) -> Rubric:
    q = select(RubricRow).where(RubricRow.workspace_id == ws, RubricRow.id == rubric_id)
    q = q.where(RubricRow.version == version) if version else q.order_by(RubricRow.version.desc())
    row = (await s.execute(q.limit(1))).scalar_one_or_none()
    if row is not None:
        return Rubric.model_validate(row.doc)
    lib = load_rubrics().get(rubric_id)
    if lib is None:
        raise not_found("rubric", rubric_id)
    return lib


def _seed(labeler: str, day: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{labeler}|{day}".encode()).digest()[:8], "big")


def _classify(doc: dict[str, Any]) -> Reason:
    small = doc.get("small_result")
    if small is not None and small != doc.get("result"):
        return "disagreement"
    conf = float(doc.get("confidence", 1.0))
    if UNCERTAIN[0] <= conf <= UNCERTAIN[1]:
        return "uncertain"
    return "random"


async def review_queue(
    s: AsyncSession,
    ws: str,
    rubric_id: str,
    labeler: str,
    limit: int = 20,
    *,
    today: str | None = None,
) -> QueueOut:
    """Disagreements first, then uncertain verdicts, plus ~10 percent uniformly random items
    (seeded by labeler and date) so agreement can be estimated without selection bias."""
    await _rubric_doc(s, ws, rubric_id, None)
    rows = (
        await s.execute(
            text(
                "SELECT v.episode_id, e.scenario_id, v.doc FROM verdicts v "
                "JOIN episodes e ON e.id = v.episode_id "
                "WHERE v.workspace_id = :ws AND v.criterion = :r AND e.status = 'done' "
                "AND v.doc->>'stage' IN ('small', 'strong') AND v.result <> 'error' "
                "AND NOT EXISTS (SELECT 1 FROM human_labels h WHERE h.episode_id = v.episode_id "
                "AND h.rubric_id = :r AND h.labeler = :lab) "
                "ORDER BY v.episode_id, v.created_at DESC"
            ),
            {"ws": ws, "r": rubric_id, "lab": labeler},
        )
    ).all()
    seen: set[str] = set()
    pool: dict[Reason, list[tuple[str, str, int | None]]] = {
        "disagreement": [],
        "uncertain": [],
        "random": [],
    }
    for ep_id, scn, doc in rows:
        if ep_id in seen:
            continue
        seen.add(ep_id)
        pool[_classify(doc)].append((ep_id, scn, doc.get("rubric_version")))
    day = today or datetime.now(UTC).date().isoformat()
    rng = random.Random(_seed(labeler, day))
    rand_pool = sorted(pool["random"])
    rng.shuffle(rand_pool)

    n_random = round(limit * RANDOM_SHARE) if limit >= 5 else (1 if limit >= 2 else 0)
    per_scn: Counter[str] = Counter()
    chosen: list[QueueItem] = []

    def take(reason: Reason, cands: list[tuple[str, str, int | None]], cap: int) -> None:
        taken = 0
        for ep_id, scn, ver in cands:
            if taken >= cap or len(chosen) >= limit:
                return
            if per_scn[scn] >= PER_SCENARIO:
                continue
            per_scn[scn] += 1
            taken += 1
            chosen.append(
                QueueItem(
                    episode_id=ep_id,
                    rubric_id=rubric_id,
                    rubric_version=ver,
                    scenario_id=scn,
                    reason=reason,
                )
            )

    take("disagreement", pool["disagreement"], limit - n_random)
    take("uncertain", pool["uncertain"], limit - n_random - len(chosen))
    take("random", rand_pool, n_random)
    # not enough signal items: top the page up with more random ones
    leftover = [c for c in rand_pool if c[0] not in {i.episode_id for i in chosen}]
    take("random", leftover, limit - len(chosen))
    return QueueOut(rubric_id=rubric_id, labeler=labeler, items=chosen)


async def get_item(
    s: AsyncSession,
    ws: str,
    episode_id: str,
    rubric_id: str,
    labeler: str,
    *,
    reveal: bool,
) -> ItemOut:
    ep = await s.get(Episode, episode_id)
    if ep is None or ep.workspace_id != ws or ep.status != "done":
        raise not_found("episode", episode_id)
    mine = (
        await s.execute(
            select(HumanLabel).where(
                HumanLabel.episode_id == episode_id,
                HumanLabel.rubric_id == rubric_id,
                HumanLabel.labeler == labeler,
            )
        )
    ).scalar_one_or_none()
    if reveal and mine is None:
        raise ApiError(403, "label_first", "label this item before revealing the judge verdict")
    inputs = await load_episode_inputs(s, episode_id)
    rubric = await _rubric_doc(s, ws, rubric_id, None)
    events = await _events(s, episode_id)
    built = build_world(inputs.world, inputs.scenario.world_overrides, int(ep.rng_seed))
    traj = build_trajectory(episode_id, inputs.scenario, events, built)
    judge: Verdict | None = None
    if reveal:
        rows = (
            await s.execute(
                select(VerdictRow.doc)
                .where(
                    VerdictRow.episode_id == episode_id,
                    VerdictRow.criterion == rubric_id,
                    VerdictRow.doc["stage"].astext != "human",
                )
                .order_by(VerdictRow.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        judge = Verdict.model_validate(rows) if rows is not None else None
    return ItemOut(
        episode_id=episode_id,
        rubric=rubric,
        scenario_id=inputs.scenario.id,
        scenario_title=inputs.scenario.title,
        goal=inputs.scenario.goal,
        transcript=render_trajectory(traj),
        my_label=mine.result if mine else None,
        judge=judge,
    )


async def recompute_outcome(s: AsyncSession, ep: Episode) -> str | None:
    """Re-apply the outcome rule to the effective verdicts (human rows override judges)."""
    if ep.outcome not in SCORED_OUTCOMES:
        return ep.outcome
    events = await _events(s, ep.id)
    rows = (
        await s.execute(
            text("SELECT doc FROM verdicts WHERE episode_id = :e ORDER BY created_at, id"),
            {"e": ep.id},
        )
    ).scalars()
    current = apply_human_override([Verdict.model_validate(d) for d in rows])
    checks = [
        (str(e.payload["check_id"]), bool(e.payload["holds"]))
        for e in events
        if e.kind == "check_result"
    ]
    ep.outcome = apply_outcome_rule(checks, current)
    return ep.outcome


async def put_label(s: AsyncSession, ws: str, labeler: str, body: LabelIn) -> LabelOut:
    ep = await s.get(Episode, body.episode_id)
    if ep is None or ep.workspace_id != ws:
        raise not_found("episode", body.episode_id)
    if ep.status != "done":
        raise ApiError(409, "episode_not_done", "only a finished episode can be labelled")
    judged = (
        await s.execute(
            text(
                "SELECT doc FROM verdicts WHERE episode_id = :e AND criterion = :r "
                "AND doc->>'stage' <> 'human' ORDER BY created_at DESC LIMIT 1"
            ),
            {"e": body.episode_id, "r": body.rubric_id},
        )
    ).scalar_one_or_none()
    rubric = await _rubric_doc(s, ws, body.rubric_id, None)
    version = judged.get("rubric_version") if judged else rubric.version
    if judged is not None and version is not None and version != rubric.version:
        rubric = await _rubric_doc(s, ws, body.rubric_id, int(version))

    label = (
        await s.execute(
            select(HumanLabel).where(
                HumanLabel.episode_id == body.episode_id,
                HumanLabel.rubric_id == body.rubric_id,
                HumanLabel.labeler == labeler,
            )
        )
    ).scalar_one_or_none()
    if label is None:
        label = HumanLabel(
            id=new_id("hl"),
            workspace_id=ws,
            episode_id=body.episode_id,
            rubric_id=body.rubric_id,
            rubric_version=version,
            result=body.result,
            labeler=labeler,
            note=body.note,
        )
        s.add(label)
    else:
        changed = label.result != body.result
        label.result, label.note = body.result, body.note
        label.rubric_version = version
        if changed:
            label.is_golden = False  # a changed label has to be re-agreed
    await s.flush()

    evaluator = f"human:{labeler}"
    await s.execute(
        delete(VerdictRow).where(
            VerdictRow.episode_id == body.episode_id,
            VerdictRow.criterion == body.rubric_id,
            VerdictRow.evaluator == evaluator,
        )
    )
    verdict = Verdict(
        evaluator=evaluator,
        rubric_version=version,
        criterion=body.rubric_id,
        result=body.result,
        severity=rubric.severity,
        hard_fail=rubric.hard_fail,
        confidence=1.0,
        reasoning=body.note or "",
        stage="human",
    )
    s.add(
        VerdictRow(
            id=new_id("vrd"),
            workspace_id=ws,
            episode_id=body.episode_id,
            evaluator=evaluator,
            criterion=body.rubric_id,
            result=body.result,
            doc=verdict.model_dump(mode="json"),
        )
    )
    await s.flush()
    before = ep.outcome
    after = await recompute_outcome(s, ep)
    await audit(
        s, ws, labeler, "review.labeled", "episode", body.episode_id,
        {"rubric_id": body.rubric_id, "result": body.result,
         "outcome_history": [before, after]},
    )  # fmt: skip
    await s.commit()
    return LabelOut(
        id=label.id,
        episode_id=label.episode_id,
        rubric_id=label.rubric_id,
        rubric_version=label.rubric_version,
        result=label.result,
        labeler=label.labeler,
        note=label.note,
        is_golden=label.is_golden,
        outcome_before=before,
        outcome_after=after,
    )
