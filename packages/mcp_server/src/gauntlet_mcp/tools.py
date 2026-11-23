"""Tool implementations. Read tools by default; the only write is the confirmed, capped
`create_run`. Nothing here deletes, changes a policy or publishes anything."""

from __future__ import annotations

import os
from typing import Any

from gauntlet_mcp.caps import cap
from gauntlet_mcp.client import ApiError, Client

DEFAULT_MAX_BUDGET_USD = 1.0


def max_budget_usd() -> float:
    try:
        return float(os.environ.get("GAUNTLET_MCP_MAX_BUDGET_USD", DEFAULT_MAX_BUDGET_USD))
    except ValueError:
        return DEFAULT_MAX_BUDGET_USD


def error(message: str) -> str:
    return cap({"error": message})


async def _guard(coro: Any) -> str:
    try:
        return cap(await coro)
    except ApiError as e:
        return error(str(e))


async def list_agents(c: Client, limit: int = 50) -> str:
    return await _guard(c.get("/v1/agents", limit=limit))


async def list_runs(
    c: Client, agent_version_id: str = "", status: str = "", limit: int = 50
) -> str:
    return await _guard(
        c.get("/v1/runs", agent_version_id=agent_version_id, status=status, limit=limit)
    )


async def get_run_report(c: Client, run_id: str) -> str:
    return await _guard(c.get(f"/v1/runs/{run_id}/report"))


async def get_episode(c: Client, episode_id: str) -> str:
    return await _guard(c.get(f"/v1/episodes/{episode_id}"))


async def list_findings(
    c: Client, severity: str = "", status: str = "", agent_version_id: str = "", limit: int = 50
) -> str:
    return await _guard(
        c.get(
            "/v1/findings",
            severity=severity,
            status=status,
            agent_version_id=agent_version_id,
            limit=limit,
        )
    )


async def get_finding(c: Client, finding_id: str) -> str:
    return await _guard(c.get(f"/v1/findings/{finding_id}"))


async def generate_scenarios(c: Client, agent_id: str) -> str:
    return await _guard(c.post(f"/v1/agents/{agent_id}/generate-scenarios"))


async def compare_runs(c: Client, run_id: str, baseline_run_id: str = "") -> str:
    return await _guard(c.get(f"/v1/runs/{run_id}/compare", baseline=baseline_run_id))


async def list_policies(c: Client) -> str:
    return await _guard(c.get("/v1/policies"))


async def create_run(
    c: Client,
    suite_id: str,
    agent_version_id: str,
    budget_usd: float | None = None,
    confirm: bool = False,
    repetitions: int | None = None,
    seed: int | None = None,
) -> str:
    """Refuses unless `confirm` is true and `budget_usd` is set and within the cap."""
    cap_usd = max_budget_usd()
    if budget_usd is None:
        return error(f"missing argument budget_usd (a positive number, at most {cap_usd})")
    if not confirm:
        return error(
            "missing argument confirm: pass confirm=true to start a run "
            f"(budget_usd={budget_usd}); runs spend money"
        )
    if budget_usd <= 0 or budget_usd > cap_usd:
        return error(
            f"budget_usd {budget_usd} outside (0, {cap_usd}] (GAUNTLET_MCP_MAX_BUDGET_USD)"
        )
    body: dict[str, Any] = {
        "suite_id": suite_id,
        "agent_version_id": agent_version_id,
        "budget_usd_micros": round(budget_usd * 1_000_000),
    }
    if repetitions is not None:
        body["repetitions"] = repetitions
    if seed is not None:
        body["seed"] = seed
    return await _guard(c.post("/v1/runs", body))
