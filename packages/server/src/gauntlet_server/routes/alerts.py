"""Alert channels, rules and alerts (P5-7). Channels reference a stored secret by name."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthCtx
from ..deps import AppState, auth_ctx, db_session, get_state
from ..services.alerts import (
    AlertOut,
    ChannelIn,
    ChannelOut,
    ChannelPatch,
    RuleIn,
    RuleOut,
    RulePatch,
    SilenceIn,
    create_channel,
    create_rule,
    list_alerts,
    list_channels,
    list_rules,
    silence_alert,
    update_channel,
    update_rule,
)

router = APIRouter(prefix="/v1")


def _actor(a: AuthCtx) -> str:
    return a.key_name or a.key_id


@router.post("/alert-channels", status_code=201, response_model=ChannelOut)
async def post_channel(
    body: ChannelIn,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> ChannelOut:
    """Opt-in delivery: the channel stores the secret's name only (never the URL)."""
    return await create_channel(state, s, auth.workspace_id, body, _actor(auth))


@router.get("/alert-channels", response_model=list[ChannelOut])
async def get_channels(
    auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> list[ChannelOut]:
    return await list_channels(s, auth.workspace_id)


@router.patch("/alert-channels/{channel_id}", response_model=ChannelOut)
async def patch_channel(
    channel_id: str,
    body: ChannelPatch,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> ChannelOut:
    return await update_channel(state, s, auth.workspace_id, channel_id, body, _actor(auth))


@router.post("/alert-rules", status_code=201, response_model=RuleOut)
async def post_rule(
    body: RuleIn, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> RuleOut:
    return await create_rule(s, auth.workspace_id, body, _actor(auth))


@router.get("/alert-rules", response_model=list[RuleOut])
async def get_rules(
    auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> list[RuleOut]:
    return await list_rules(s, auth.workspace_id)


@router.patch("/alert-rules/{rule_id}", response_model=RuleOut)
async def patch_rule(
    rule_id: str,
    body: RulePatch,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> RuleOut:
    return await update_rule(s, auth.workspace_id, rule_id, body, _actor(auth))


@router.get("/alerts", response_model=list[AlertOut])
async def get_alerts(
    state: str | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> list[AlertOut]:
    return await list_alerts(s, auth.workspace_id, state)


@router.post("/alerts/{alert_id}/silence", response_model=AlertOut)
async def post_silence(
    alert_id: str,
    body: SilenceIn,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> AlertOut:
    """Silences the alert's rule (all its alerts) until the given time."""
    return await silence_alert(s, auth.workspace_id, alert_id, body.until, _actor(auth))
