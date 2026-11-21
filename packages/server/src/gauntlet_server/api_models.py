"""Response models of the `/v1` api. They exist so the OpenAPI document types every response
(the web client is generated from it). Document shapes reuse `gauntlet_core.schema` and
`gauntlet_core.eval.report`; only list envelopes and the server's own rows are defined here.
Timestamps are ISO-8601 strings, as the routes have always sent them."""

from __future__ import annotations

from typing import Literal

from gauntlet_core.llm.catalog import CatalogModel, RoleChoice
from gauntlet_core.schema import (
    AgentVersion,
    Event,
    Outcome,
    Persona,
    Rubric,
    RunManifest,
    Scenario,
    StateDiff,
    Suite,
    Termination,
    Verdict,
    WorldSpec,
)
from pydantic import BaseModel, ConfigDict

__all__ = [
    "AgentList",
    "AgentOut",
    "AgentVersionList",
    "AgentVersionOut",
    "ApiKeyCreated",
    "ApiKeyList",
    "ApiKeyOut",
    "DryRunOut",
    "EpisodeDetail",
    "EpisodeList",
    "EpisodeRow",
    "EpisodeScenario",
    "Estimate",
    "ModelCatalogOut",
    "ModelSettingsIn",
    "ModelSettingsOut",
    "PersonaDoc",
    "PersonaList",
    "ProjectList",
    "ProjectOut",
    "RubricDoc",
    "RubricList",
    "RunCounts",
    "RunList",
    "RunOut",
    "ScenarioList",
    "ScenarioRecord",
    "SecretList",
    "SecretOut",
    "SecretPut",
    "SeedOut",
    "SuiteList",
    "SuiteOut",
    "WhoAmI",
    "WorldDoc",
    "WorldList",
]


class _Out(BaseModel):
    """Own response rows declare every field without a default: always present, maybe null."""

    model_config = ConfigDict(extra="forbid")


class Paginated[T](_Out):
    """`{items, next_cursor}`; `next_cursor` is null on the last page."""

    items: list[T]
    next_cursor: str | None


class WhoAmI(_Out):
    workspace_id: str
    key_id: str | None
    key_name: str | None
    scopes: list[str]
    default_project_id: str | None


class ProjectOut(_Out):
    id: str
    name: str
    created_at: str


class ProjectList(Paginated[ProjectOut]):
    pass


class AgentOut(_Out):
    id: str
    project_id: str
    name: str
    latest_version_id: str | None
    purpose: str | None  # the latest version's profile purpose
    created_at: str


class AgentList(Paginated[AgentOut]):
    pass


class AgentVersionOut(AgentVersion):
    world_id: str | None
    created_at: str


class AgentVersionList(Paginated[AgentVersionOut]):
    pass


class SecretOut(_Out):
    name: str
    created_at: str | None


class SecretList(Paginated[SecretOut]):
    pass


class SecretPut(_Out):
    name: str


class ApiKeyOut(_Out):
    id: str
    name: str | None
    prefix: str | None
    created_at: str | None


class ApiKeyList(Paginated[ApiKeyOut]):
    pass


class ApiKeyCreated(_Out):
    id: str
    name: str | None
    prefix: str | None
    key: str  # shown once


# versioned documents: the stored document plus its version and creation time
class WorldDoc(WorldSpec):
    version: int
    created_at: str


class WorldList(Paginated[WorldDoc]):
    pass


class PersonaDoc(Persona):
    version: int
    created_at: str


class PersonaList(Paginated[PersonaDoc]):
    pass


class RubricDoc(Rubric):
    created_at: str


class RubricList(Paginated[RubricDoc]):
    pass


class ScenarioRecord(_Out):
    scenario: Scenario
    id: str
    status: Literal["draft", "approved"]
    source: Literal["pack", "generated", "mined", "pinned"]
    version: int
    created_at: str


class ScenarioList(Paginated[ScenarioRecord]):
    pass


class SuiteOut(Suite):
    created_at: str


class SuiteList(Paginated[SuiteOut]):
    pass


RunStatus = Literal["queued", "running", "paused", "cancelled", "done", "failed"]
EpisodeStatus = Literal["queued", "leased", "done", "cancelled"]


class RunCounts(_Out):
    total: int
    queued: int
    leased: int
    done: int
    cancelled: int
    by_outcome: dict[str, int]


class Estimate(_Out):
    low: int
    expected: int
    high: int


class RunOut(_Out):
    id: str
    suite_id: str
    agent_version_id: str
    status: RunStatus
    manifest: RunManifest
    repetitions: int
    seed: int
    budget_usd_micros: int
    reserved_usd_micros: int
    spent_usd_micros: int
    baseline_of: str | None
    purpose: str = "eval"
    finding_id: str | None = None
    adaptive: bool = False
    counts: RunCounts
    created_at: str
    finished_at: str | None
    estimate_usd_micros: Estimate | None = None  # on creation
    warnings: list[str] | None = None  # on creation


class RunList(Paginated[RunOut]):
    pass


class DryRunOut(_Out):
    valid: bool
    errors: list[dict[str, str]]
    warnings: list[str]
    episode_count: int
    estimate_usd_micros: Estimate


class EpisodeRow(_Out):
    id: str
    run_id: str
    scenario_id: str
    scenario_version: int | None
    rep: int
    status: EpisodeStatus
    outcome: Outcome | None
    termination: Termination | None
    attempt: int
    cost_usd_micros: int
    world_fidelity: str | None
    created_at: str
    finished_at: str | None


class EpisodeList(Paginated[EpisodeRow]):
    pass


class EpisodeScenario(_Out):
    id: str
    title: str
    goal: str
    max_turns: int
    tags: dict[str, str]


class EpisodeDetail(EpisodeRow):
    scenario: EpisodeScenario
    partial: bool
    events: list[Event]
    verdicts: list[Verdict]
    diff: StateDiff
    tools: dict[str, str]  # tool name -> risk


class SeedOut(_Out):
    api_key_hint: str | None
    project_id: str
    agent_id: str
    agent_version_id: str
    suite_id: str
    run_id: str
    compare_run_id: str | None = None
    failed_episode_id: str | None


class ModelCatalogOut(_Out):
    models: list[CatalogModel]


class ModelSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    roles: dict[str, RoleChoice]


class ModelSettingsOut(_Out):
    roles: dict[str, RoleChoice]  # resolved: workspace choice over gauntlet.toml over defaults
    overridden: list[str]  # roles the workspace has set itself
