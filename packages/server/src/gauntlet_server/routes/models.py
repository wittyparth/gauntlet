"""Model catalog and per-workspace role settings."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from gauntlet_core.llm.catalog import CATALOG, SETTABLE_ROLES, catalog_model
from sqlalchemy.ext.asyncio import AsyncSession

from ..api_models import ModelCatalogOut, ModelSettingsIn, ModelSettingsOut
from ..auth import AuthCtx
from ..deps import AppState, auth_ctx, db_session, get_state
from ..errors import ApiError
from ..services.model_settings import effective_config, load_choices, resolved_roles, store_choices

router = APIRouter(prefix="/v1")


@router.get("/models/catalog", response_model=ModelCatalogOut)
async def model_catalog(_: AuthCtx = Depends(auth_ctx)) -> dict[str, Any]:
    return {"models": [m.model_dump(mode="json") for m in CATALOG]}


async def _settings(session: AsyncSession, state: AppState, workspace_id: str) -> dict[str, Any]:
    choices = await load_choices(session, workspace_id)
    cfg = effective_config(state.gateway_config, choices)
    return {
        "roles": resolved_roles(cfg),
        "overridden": [r for r in SETTABLE_ROLES if r in choices],
    }


@router.get("/settings/models", response_model=ModelSettingsOut)
async def get_model_settings(
    auth: AuthCtx = Depends(auth_ctx),
    session: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> dict[str, Any]:
    return await _settings(session, state, auth.workspace_id)


@router.put("/settings/models", response_model=ModelSettingsOut)
async def put_model_settings(
    body: ModelSettingsIn,
    auth: AuthCtx = Depends(auth_ctx),
    session: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> dict[str, Any]:
    """Replaces the workspace's choices; roles not listed fall back to the defaults, so an
    empty `roles` resets everything."""
    errors: list[dict[str, str]] = []
    for role, choice in body.roles.items():
        cm = catalog_model(choice.model)
        if role not in SETTABLE_ROLES:
            errors.append({"role": role, "code": "unknown_role", "message": "cannot be set"})
        elif cm is None:
            errors.append(
                {"role": role, "code": "unknown_model", "message": "not in the model catalog"}
            )
        elif choice.reasoning == "off" and not cm.supports_reasoning_off:
            errors.append(
                {"role": role, "code": "reasoning_off_unsupported", "message": "reasoning is on"}
            )
    if errors:
        raise ApiError(422, "validation_error", "invalid model settings", errors)
    await store_choices(session, auth.workspace_id, body.roles)
    await session.commit()
    return await _settings(session, state, auth.workspace_id)
