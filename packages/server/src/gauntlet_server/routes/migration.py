"""Model migration report and Pareto data (P3-8)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthCtx
from ..deps import auth_ctx, db_session
from ..services.migration import MigrationReport, ParetoOut, migration_report, pareto

router = APIRouter(prefix="/v1")


@router.get("/runs/{run_id}/migration", response_model=MigrationReport)
async def get_migration(
    run_id: str,
    baseline: str,
    force: bool = False,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> MigrationReport:
    """Is it safe to move from the baseline run's agent version to this run's?"""
    return await migration_report(s, auth.workspace_id, run_id, baseline, force)


@router.get("/migrations/pareto", response_model=ParetoOut)
async def get_pareto(
    run_ids: str,
    metrics: str = "pass_rate,cost",
    force: bool = False,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> ParetoOut:
    ids = [r for r in (x.strip() for x in run_ids.split(",")) if r]
    ms = [m for m in (x.strip() for x in metrics.split(",")) if m]
    return await pareto(s, auth.workspace_id, ids, ms, force)
