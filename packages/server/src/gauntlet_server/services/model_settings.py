"""Workspace model settings: the workspace's role choices over `gauntlet.toml` over defaults."""

from __future__ import annotations

from typing import Any

from gauntlet_core.llm import GatewayConfig
from gauntlet_core.llm.catalog import SETTABLE_ROLES, RoleChoice, apply_role_settings
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import WorkspaceSettings

__all__ = ["effective_config", "load_choices", "resolved_roles", "store_choices"]


async def load_choices(session: AsyncSession, workspace_id: str) -> dict[str, RoleChoice]:
    row = await session.get(WorkspaceSettings, workspace_id)
    if row is None:
        return {}
    return {r: RoleChoice.model_validate(c) for r, c in row.model_roles.items()}


async def store_choices(
    session: AsyncSession, workspace_id: str, choices: dict[str, RoleChoice]
) -> None:
    doc = {r: c.model_dump(mode="json") for r, c in choices.items()}
    row = await session.get(WorkspaceSettings, workspace_id)
    if row is None:
        session.add(WorkspaceSettings(workspace_id=workspace_id, model_roles=doc))
    else:
        row.model_roles = doc
    await session.flush()


def effective_config(base: GatewayConfig, choices: dict[str, RoleChoice]) -> GatewayConfig:
    return apply_role_settings(base, choices) if choices else base


def resolved_roles(config: GatewayConfig) -> dict[str, dict[str, Any]]:
    """{role: {model, reasoning}} for the configurable roles."""
    return {
        r: {"model": config.llm.roles[r].model, "reasoning": config.llm.roles[r].reasoning}
        for r in SETTABLE_ROLES
    }
