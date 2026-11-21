"""Attack-scope controls and run-creation enforcement for attack runs (P2-4)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from gauntlet_core.schema import AgentVersion, Scenario
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Run, WorkspaceSettings
from ..deps import AppState
from ..errors import ApiError
from .killswitch import killswitch_engaged
from .ownership import require_target_verified

__all__ = [
    "AttackScope",
    "WorkspaceDoc",
    "enforce_attack_run",
    "is_attack_run",
    "load_attack_scope",
    "load_doc",
    "store_doc",
]


class AttackScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_categories: list[str] | None = None
    max_episodes_per_run: int = Field(default=2000, ge=1)
    max_run_budget_usd_micros: int = Field(default=20_000_000, ge=1)
    adaptive_enabled: bool = True
    max_concurrent_attack_runs: int = Field(default=2, ge=1)


class WorkspaceDoc(BaseModel):
    attack_scope: AttackScope = AttackScope()
    auto_pin_on_fixed: bool = True


def is_attack_run(scenarios: Sequence[Scenario]) -> bool:
    return any(s.attack is not None for s in scenarios)


async def load_doc(session: AsyncSession, workspace_id: str) -> WorkspaceDoc:
    row = await session.get(WorkspaceSettings, workspace_id)
    return WorkspaceDoc.model_validate(row.doc if row is not None and row.doc else {})


async def store_doc(session: AsyncSession, workspace_id: str, doc: WorkspaceDoc) -> None:
    data: dict[str, Any] = doc.model_dump(mode="json")
    row = await session.get(WorkspaceSettings, workspace_id)
    if row is None:
        session.add(WorkspaceSettings(workspace_id=workspace_id, doc=data))
    else:
        row.doc = data
    await session.flush()


async def load_attack_scope(session: AsyncSession, workspace_id: str) -> AttackScope:
    return (await load_doc(session, workspace_id)).attack_scope


async def enforce_attack_run(
    session: AsyncSession,
    state: AppState,
    workspace_id: str,
    version: AgentVersion,
    scenarios: Sequence[Scenario],
    *,
    episodes: int,
    budget_usd_micros: int,
) -> None:
    """Raises 423 killswitch/disabled, 403 target_not_verified, 422 scope_violation."""
    if state.settings.attacks_disabled:
        raise ApiError(423, "attacks_disabled", "attack runs are disabled by the operator")
    if state.redis is not None and await killswitch_engaged(state.redis, workspace_id):
        raise ApiError(423, "killswitch_engaged", "the kill switch is engaged")
    await require_target_verified(session, state.settings, workspace_id, version.target)
    scope = await load_attack_scope(session, workspace_id)

    def violation(key: str, message: str) -> ApiError:
        return ApiError(422, "scope_violation", message, {"key": key})

    if scope.allowed_categories is not None:
        cats = {s.tags.get("attack_category") for s in scenarios if s.attack is not None}
        bad = sorted(str(c) for c in cats if c not in scope.allowed_categories)
        if bad:
            raise violation("allowed_categories", f"categories not allowed: {bad}")
    if episodes > scope.max_episodes_per_run:
        raise violation("max_episodes_per_run", f"{episodes} episodes exceed the scope limit")
    if budget_usd_micros > scope.max_run_budget_usd_micros:
        raise violation("max_run_budget_usd_micros", "budget exceeds the scope limit")
    active = (
        await session.execute(
            select(func.count())
            .select_from(Run)
            .where(
                Run.workspace_id == workspace_id,
                Run.attack.is_(True),
                Run.status.in_(("queued", "running", "paused")),
            )
        )
    ).scalar_one()
    if active >= scope.max_concurrent_attack_runs:
        raise violation("max_concurrent_attack_runs", "too many attack runs are active")
