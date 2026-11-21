"""Failure clusters of a run (P3-6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthCtx
from ..deps import AppState, auth_ctx, db_session, get_state
from ..services.clusters import ClustersOut, ClusterStarted, clusters_for_run, enqueue_cluster

router = APIRouter(prefix="/v1")


@router.post("/runs/{run_id}/cluster", status_code=202, response_model=ClusterStarted)
async def post_cluster(
    run_id: str,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> ClusterStarted:
    """Idempotent per run: running it again replaces the run's clusters."""
    job_id = await enqueue_cluster(
        state, s, auth.workspace_id, run_id, auth.key_name or auth.key_id
    )
    return ClusterStarted(job_id=job_id)


@router.get("/runs/{run_id}/clusters", response_model=ClustersOut)
async def get_clusters(
    run_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> ClustersOut:
    return await clusters_for_run(s, auth.workspace_id, run_id)
