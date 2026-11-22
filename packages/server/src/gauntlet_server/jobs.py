"""Rebuild everything an episode needs from the database. Shared by the worker (to run the
episode) and the api facade (to fold the world from the journal)."""

from __future__ import annotations

import re

from gauntlet_core.eval import load_rubrics
from gauntlet_core.runner import EpisodeJob
from gauntlet_core.schema import (
    AgentVersion,
    Persona,
    Policy,
    Rubric,
    RunManifest,
    Scenario,
    WorldSpec,
)
from gauntlet_core.sim import load_persona_library
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import Episode, Run
from .db.models import Persona as PersonaRow
from .db.models import Rubric as RubricRow
from .db.models import Scenario as ScenarioRow
from .db.models import World as WorldRow
from .db.policy_models import PolicyVersion
from .secrets import SecretStore
from .services.calibration_state import apply_calibration, judge_models

__all__ = ["JobInputs", "load_episode_inputs", "load_episode_job", "secret_names"]

_SECRET_REF = re.compile(r"\{\{\s*secret:([A-Za-z0-9_.-]+)\s*\}\}")


class JobInputs:
    """Plain data of one episode, before secrets are decrypted."""

    def __init__(
        self,
        episode: Episode,
        run: Run,
        manifest: RunManifest,
        scenario: Scenario,
        world: WorldSpec,
        persona: Persona,
        rubrics: dict[str, Rubric],
    ) -> None:
        self.episode, self.run, self.manifest = episode, run, manifest
        self.scenario, self.world, self.persona, self.rubrics = scenario, world, persona, rubrics


def secret_names(version: AgentVersion) -> set[str]:
    cfg = version.target
    names: set[str] = set()
    if cfg.kind == "openai_compat" and cfg.api_key_secret:
        names.add(cfg.api_key_secret)
    if cfg.kind == "http":
        for v in cfg.headers.values():
            names.update(_SECRET_REF.findall(v))
    return names


async def load_episode_inputs(session: AsyncSession, episode_id: str) -> JobInputs:
    ep = await session.get(Episode, episode_id)
    if ep is None:
        raise LookupError(f"episode {episode_id} not found")
    run = await session.get(Run, ep.run_id)
    assert run is not None
    manifest = RunManifest.model_validate(run.manifest)
    row = await session.get(ScenarioRow, (ep.scenario_id, ep.scenario_version or 1))
    if row is None:
        raise LookupError(f"scenario {ep.scenario_id} v{ep.scenario_version} not found")
    scenario = Scenario.model_validate(row.doc)
    if isinstance(scenario.world, str):
        world_id = scenario.world
        version = run.world_versions.get(world_id)
        wrow = await session.get(WorldRow, (world_id, version)) if version else None
        if wrow is None:
            raise LookupError(f"world {world_id} not pinned for run {run.id}")
        world = WorldSpec.model_validate(wrow.doc)
    else:
        world = scenario.world
    persona = await _persona(session, run.workspace_id, scenario.persona)
    rubrics = await _rubrics(session, run.workspace_id, scenario.rubrics)
    rubrics = await apply_calibration(
        session, run.workspace_id, rubrics, judge_models(manifest.model_roles)
    )
    return JobInputs(ep, run, manifest, scenario, world, persona, rubrics)


async def _persona(session: AsyncSession, workspace_id: str, persona_id: str) -> Persona:
    row = (
        await session.execute(
            select(PersonaRow)
            .where(PersonaRow.workspace_id == workspace_id, PersonaRow.id == persona_id)
            .order_by(PersonaRow.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is not None:
        return Persona.model_validate(row.doc)
    library = load_persona_library()
    if persona_id not in library:
        raise LookupError(f"persona {persona_id} not found")
    return library[persona_id]


async def _rubrics(session: AsyncSession, workspace_id: str, ids: list[str]) -> dict[str, Rubric]:
    library = load_rubrics()
    out = {i: library[i] for i in ids if i in library}
    for rid in ids:
        if rid in out:
            continue
        row = (
            await session.execute(
                select(RubricRow)
                .where(RubricRow.workspace_id == workspace_id, RubricRow.id == rid)
                .order_by(RubricRow.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            raise LookupError(f"rubric {rid} not found")
        out[rid] = Rubric.model_validate(row.doc)
    return out


async def load_episode_job(
    session: AsyncSession, episode_id: str, secrets: SecretStore | None = None
) -> EpisodeJob:
    i = await load_episode_inputs(session, episode_id)
    names = secret_names(i.manifest.agent_version)
    resolved = (
        await secrets.resolve(i.run.workspace_id, names) if secrets is not None and names else {}
    )
    policy = None
    if i.run.policy_id:
        prow = await session.get(PolicyVersion, (i.run.policy_id, i.run.policy_version or 1))
        if prow is not None:
            policy = Policy.model_validate(prow.doc)
    return EpisodeJob(
        episode_id=episode_id,
        run_id=i.run.id,
        scenario=i.scenario,
        world=i.world,
        agent_version=i.manifest.agent_version,
        persona=i.persona,
        rubrics=i.rubrics,
        rng_seed=int(i.episode.rng_seed),
        secrets=resolved,
        policy=policy,
        # verification runs enforce even a stored shadow policy (P4-5)
        policy_mode_override="enforce" if i.run.purpose in ("verify", "verify_benign") else None,
    )
