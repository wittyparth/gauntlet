"""Policy compiler and review flow (P4-1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from gauntlet_core.policy.compile import CompiledPolicy, CoverageReport
from gauntlet_core.schema import PolicyRule
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthCtx
from ..deps import AppState, auth_ctx, db_session, get_state
from ..services.policies import (
    CompileIn,
    CompileStarted,
    PatchIn,
    PolicyOut,
    PublishIn,
    coverage_for,
    enqueue_compile,
    get_policy,
    get_proposals,
    list_policies,
    patch_proposal,
    publish_policy,
)
from ..services.policy_rules import add_rule, delete_rule, replace_rule

router = APIRouter(prefix="/v1/policies")


def _actor(auth: AuthCtx) -> str:
    return auth.key_name or auth.key_id


@router.post("/compile", status_code=202, response_model=CompileStarted)
async def post_compile(
    body: CompileIn,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
    state: AppState = Depends(get_state),
) -> CompileStarted:
    """Queues a `compile_policy` job; the result is a draft policy with reviewable proposals."""
    return await enqueue_compile(state, s, auth.workspace_id, body, _actor(auth))


@router.get("", response_model=list[PolicyOut])
async def get_policies(
    auth: AuthCtx = Depends(auth_ctx), s: AsyncSession = Depends(db_session)
) -> list[PolicyOut]:
    return await list_policies(s, auth.workspace_id)


@router.get("/{policy_id}", response_model=PolicyOut)
async def get_one(
    policy_id: str,
    version: int | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> PolicyOut:
    return await get_policy(s, auth.workspace_id, policy_id, version)


@router.get("/{policy_id}/proposals", response_model=CompiledPolicy)
async def get_policy_proposals(
    policy_id: str,
    version: int | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> CompiledPolicy:
    return await get_proposals(s, auth.workspace_id, policy_id, version)


@router.patch("/{policy_id}/proposals/{clause_id}", response_model=CompiledPolicy)
async def patch_one(
    policy_id: str,
    clause_id: str,
    body: PatchIn,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> CompiledPolicy:
    """Accept, reject or edit one proposal. An edit is validated like a compiled rule."""
    return await patch_proposal(s, auth.workspace_id, policy_id, clause_id, body, _actor(auth))


@router.post("/{policy_id}/publish", status_code=201, response_model=PolicyOut)
async def post_publish(
    policy_id: str,
    body: PublishIn | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> PolicyOut:
    return await publish_policy(s, auth.workspace_id, policy_id, body or PublishIn(), _actor(auth))


@router.get("/{policy_id}/coverage", response_model=CoverageReport)
async def get_coverage(
    policy_id: str,
    version: int | None = None,
    run_id: str | None = None,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> CoverageReport:
    """`run_id` adds that run's trajectories to the exercised/untested and false-positive
    analysis; without it only the clause counts are filled in."""
    return await coverage_for(s, auth.workspace_id, policy_id, version, run_id)


@router.post("/{policy_id}/rules", status_code=201, response_model=CompiledPolicy)
async def post_rule(
    policy_id: str,
    body: PolicyRule,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> CompiledPolicy:
    """Add a rule (for example a finding's suggested rule) as an accepted proposal of the draft."""
    return await add_rule(s, auth.workspace_id, policy_id, body, _actor(auth))


@router.patch("/{policy_id}/rules/{rule_id}", response_model=CompiledPolicy)
async def patch_rule(
    policy_id: str,
    rule_id: str,
    body: PolicyRule,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> CompiledPolicy:
    return await replace_rule(s, auth.workspace_id, policy_id, rule_id, body, _actor(auth))


@router.delete("/{policy_id}/rules/{rule_id}", response_model=CompiledPolicy)
async def remove_rule(
    policy_id: str,
    rule_id: str,
    auth: AuthCtx = Depends(auth_ctx),
    s: AsyncSession = Depends(db_session),
) -> CompiledPolicy:
    return await delete_rule(s, auth.workspace_id, policy_id, rule_id, _actor(auth))
