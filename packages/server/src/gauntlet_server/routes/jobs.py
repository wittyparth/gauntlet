"""Background job status (P3-5)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthCtx
from ..db.review_models import Job
from ..deps import auth_ctx, db_session
from ..errors import not_found

router = APIRouter(prefix="/v1")


class JobOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    kind: str
    status: str
    result: dict[str, Any] | None
    error: str | None
    attempts: int
    created_at: str
    finished_at: str | None


def job_json(j: Job) -> dict[str, Any]:
    return {
        "id": j.id,
        "kind": j.kind,
        "status": j.status,
        "result": j.result,
        "error": j.error,
        "attempts": j.attempts,
        "created_at": j.created_at.isoformat(),
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
    }


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(
    job_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    j = await s.get(Job, job_id)
    if j is None or j.workspace_id != auth.workspace_id:
        raise not_found("job", job_id)
    return job_json(j)
