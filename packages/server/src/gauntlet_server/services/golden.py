"""Golden sets (P3-5): human labels that every labeler of an item agrees on (or that an
`adjudicated:` label settled) become the reference the calibration job measures judges against."""

from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from typing import Literal

from gauntlet_core.stats import cohens_kappa
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.review_models import HumanLabel

__all__ = [
    "GOLDEN_MIN_ITEMS",
    "GOLDEN_MIN_PER_CLASS",
    "GoldenIn",
    "GoldenItemRow",
    "GoldenOut",
    "GoldenSummary",
    "golden_items",
    "golden_summary",
    "mark_golden",
]

GOLDEN_MIN_ITEMS = 40
GOLDEN_MIN_PER_CLASS = 10
MIN_SHARED = 10
ADJUDICATED = "adjudicated:"


class GoldenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episode_ids: list[str]


class GoldenOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted: list[str]
    needs_adjudication: list[str]
    missing: list[str]


class LabelerKappa(BaseModel):
    model_config = ConfigDict(extra="forbid")
    labelers: tuple[str, str]
    shared: int
    kappa: float


class GoldenSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rubric_id: str
    items: int
    by_class: dict[str, int]
    labelers: int
    labeler_kappa: list[LabelerKappa]
    needs_adjudication: list[str]
    ready: bool
    readiness: str


class GoldenItemRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episode_id: str
    result: Literal["pass", "fail", "na"]


def _resolve(labels: list[HumanLabel]) -> str | None:
    """The settled result of one item, or None while labelers conflict."""
    adjudicated = [x for x in labels if (x.note or "").startswith(ADJUDICATED)]
    if adjudicated:
        return max(adjudicated, key=lambda x: x.created_at).result
    results = {x.result for x in labels}
    return results.pop() if len(results) == 1 else None


async def _labels(s: AsyncSession, ws: str, rubric_id: str) -> dict[str, list[HumanLabel]]:
    rows = (
        (
            await s.execute(
                select(HumanLabel)
                .where(HumanLabel.workspace_id == ws, HumanLabel.rubric_id == rubric_id)
                .order_by(HumanLabel.episode_id, HumanLabel.labeler)
            )
        )
        .scalars()
        .all()
    )
    by_ep: dict[str, list[HumanLabel]] = defaultdict(list)
    for r in rows:
        by_ep[r.episode_id].append(r)
    return by_ep


async def mark_golden(
    s: AsyncSession, ws: str, rubric_id: str, episode_ids: list[str]
) -> GoldenOut:
    by_ep = await _labels(s, ws, rubric_id)
    out = GoldenOut(accepted=[], needs_adjudication=[], missing=[])
    for ep in dict.fromkeys(episode_ids):
        labels = by_ep.get(ep)
        if not labels:
            out.missing.append(ep)
        elif _resolve(labels) is None:
            out.needs_adjudication.append(ep)
        else:
            out.accepted.append(ep)
    if out.accepted:
        await s.execute(
            update(HumanLabel)
            .where(
                HumanLabel.workspace_id == ws,
                HumanLabel.rubric_id == rubric_id,
                HumanLabel.episode_id.in_(out.accepted),
            )
            .values(is_golden=True)
        )
    await s.commit()
    return out


async def golden_items(
    s: AsyncSession, ws: str, rubric_id: str, version: int | None = None
) -> list[GoldenItemRow]:
    """Golden episodes with their settled result. `version` keeps only labels made against that
    rubric version (a label of another version says nothing about this document)."""
    by_ep = await _labels(s, ws, rubric_id)
    items: list[GoldenItemRow] = []
    for ep, labels in sorted(by_ep.items()):
        if not all(x.is_golden for x in labels) or (
            version is not None and any(x.rubric_version != version for x in labels)
        ):
            continue  # a relabelled item has to be accepted again
        res = _resolve(labels)
        if res is not None:
            items.append(GoldenItemRow(episode_id=ep, result=res))  # type: ignore[arg-type]
    return items


def readiness(items: list[GoldenItemRow]) -> tuple[bool, str]:
    n_fail = sum(1 for i in items if i.result == "fail")
    n_other = len(items) - n_fail
    short = []
    if len(items) < GOLDEN_MIN_ITEMS:
        short.append(f"{len(items)} of {GOLDEN_MIN_ITEMS} items")
    if n_fail < GOLDEN_MIN_PER_CLASS:
        short.append(f"{n_fail} of {GOLDEN_MIN_PER_CLASS} fail items")
    if n_other < GOLDEN_MIN_PER_CLASS:
        short.append(f"{n_other} of {GOLDEN_MIN_PER_CLASS} non-fail items")
    if short:
        return False, "not ready to gate: " + ", ".join(short)
    return True, f"ready: {len(items)} items, {n_fail} fail, {n_other} non-fail"


async def golden_summary(s: AsyncSession, ws: str, rubric_id: str) -> GoldenSummary:
    by_ep = await _labels(s, ws, rubric_id)
    items = await golden_items(s, ws, rubric_id)
    counts = Counter(i.result for i in items)
    labelers = sorted({x.labeler for ls in by_ep.values() for x in ls})
    per: dict[str, dict[str, bool]] = defaultdict(dict)  # labeler -> episode -> is fail
    for ep, ls in by_ep.items():
        for x in ls:
            per[x.labeler][ep] = x.result == "fail"
    kappas: list[LabelerKappa] = []
    for a, b in combinations(labelers, 2):
        shared = sorted(set(per[a]) & set(per[b]))
        if len(shared) >= MIN_SHARED:
            k = cohens_kappa([per[a][e] for e in shared], [per[b][e] for e in shared])
            kappas.append(LabelerKappa(labelers=(a, b), shared=len(shared), kappa=k))
    pending = sorted(ep for ep, ls in by_ep.items() if _resolve(ls) is None)
    ok, line = readiness(items)
    return GoldenSummary(
        rubric_id=rubric_id,
        items=len(items),
        by_class={k: counts.get(k, 0) for k in ("pass", "fail", "na")},
        labelers=len(labelers),
        labeler_kappa=kappas,
        needs_adjudication=pending,
        ready=ok,
        readiness=line,
    )
