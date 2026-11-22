"""The closed loop (P4-5): suggest, test, enforce, verify; and blast radius."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from gauntlet_core.policy.blast import BlastRadius, PermissionDiff
from sqlalchemy.ext.asyncio import AsyncSession

from ..api_models import RunOut
from ..auth import AuthCtx
from ..deps import AppState, auth_ctx, db_session, get_state
from ..services.blast import blast_for_version, diff_versions
from ..services.loop import (
    EnforceIn,
    JobStarted,
    PolicyTestIn,
    PolicyTestOut,
    VerifyIn,
    enforce_policy,
    enqueue_policy_test,
    enqueue_suggest,
    get_policy_test,
    list_policy_tests,
    verify_with_policy,
)
from ..services.policies import PolicyOut

router = APIRouter(prefix="/v1")


def _actor(auth: AuthCtx) -> str:
    return auth.key_name or auth.key_id


@router.post("/findings/{finding_id}/suggest-policy", status_code=202, response_model=JobStarted)
async def suggest_policy(
    finding_id: str,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> JobStarted:
    """Queues a job that turns the finding's objective into a draft shadow policy."""
    return await enqueue_suggest(state, s, auth.workspace_id, finding_id, _actor(auth))


@router.post("/policies/{policy_id}/test", status_code=202, response_model=PolicyTestOut)
async def post_policy_test(
    policy_id: str,
    body: PolicyTestIn,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> PolicyTestOut:
    """An offline test over stored trajectories. A counterfactual approximation: the result
    says so in its `approximation` field."""
    return await enqueue_policy_test(state, s, auth.workspace_id, policy_id, body, _actor(auth))


@router.get("/policies/{policy_id}/tests", response_model=list[PolicyTestOut])
async def get_policy_tests(
    policy_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> list[PolicyTestOut]:
    return await list_policy_tests(s, auth.workspace_id, policy_id)


@router.get("/policy-tests/{test_id}", response_model=PolicyTestOut)
async def get_one_policy_test(
    test_id: str, auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> PolicyTestOut:
    return await get_policy_test(s, auth.workspace_id, test_id)


@router.post("/policies/{policy_id}/enforce", status_code=201, response_model=PolicyOut)
async def post_enforce(
    policy_id: str,
    body: EnforceIn | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> PolicyOut:
    """Publishes an `enforce` version only after a passing offline test (or `override`)."""
    return await enforce_policy(
        s, state, auth.workspace_id, policy_id, body or EnforceIn(), _actor(auth)
    )


@router.post("/findings/{finding_id}/verify-with-policy", status_code=201, response_model=RunOut)
async def post_verify_with_policy(
    finding_id: str,
    body: VerifyIn,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> dict[str, Any]:
    return await verify_with_policy(s, state, auth.workspace_id, finding_id, body, _actor(auth))


@router.get("/agents/{agent_id}/versions/{version_id}/blast-radius", response_model=BlastRadius)
async def get_blast_radius(
    agent_id: str,
    version_id: str,
    policy_id: str | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> BlastRadius:
    return await blast_for_version(s, auth.workspace_id, agent_id, version_id, policy_id)


@router.get("/agents/{agent_id}/permission-diff", response_model=PermissionDiff)
async def get_permission_diff(
    agent_id: str,
    from_version: str = Query(alias="from"),
    to_version: str = Query(alias="to"),
    policy_id: str | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> PermissionDiff:
    return await diff_versions(s, auth.workspace_id, agent_id, from_version, to_version, policy_id)
