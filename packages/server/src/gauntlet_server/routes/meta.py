"""Public, read-only benchmark results (P5-5). No authentication, no workspace data."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from ..deps import AppState, get_state
from ..services.meta import BenchmarksOut, load_benchmarks

router = APIRouter(prefix="/v1/meta")


@router.get("/benchmarks", response_model=BenchmarksOut)
async def get_benchmarks(response: Response, state: AppState = Depends(get_state)) -> BenchmarksOut:
    """The committed study results with their intervals and limitations (empty when none)."""
    response.headers["Cache-Control"] = "public, max-age=300"
    return load_benchmarks(state.settings.benchmarks_dir)
