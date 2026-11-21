"""Cassettes with a self-contained manifest, strict replay, `agent_live` replay and rejudging
(P3-3, hard-cores 1.6).

A cassette is the journal as JSON Lines (`engine.cassette`) whose header carries everything
needed to rebuild the world and the trajectory offline. Strict replay re-runs the episode
pipeline over it with no way to reach a model; `agent_live` replay copies it into a fresh
episode and lets a new agent version run live (see `engine/live.py`)."""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from gauntlet_core.engine import (
    JournalSnapshot,
    MemoryJournalStore,
    NonDeterminism,
    PermanentEffectError,
    dump_cassette,
    fork_for_agent_live,
)
from gauntlet_core.engine.cassette import FORMAT
from gauntlet_core.eval.rubrics import RULE_STAGE, rule_context
from gauntlet_core.judges import JudgeEvaluator
from gauntlet_core.llm import Gateway
from gauntlet_core.runner import EpisodeJob, EpisodeOutcome, RunnerDeps, execute_episode
from gauntlet_core.schema import (
    AgentVersion,
    EffectRecord,
    Event,
    Outcome,
    Persona,
    Rubric,
    Scenario,
    Trajectory,
    Verdict,
    WorldSpec,
)
from gauntlet_core.world import build_trajectory, build_world

__all__ = [
    "CassetteError",
    "CassetteManifest",
    "Divergence",
    "ReplayReport",
    "StrictGateway",
    "apply_outcome_rule",
    "export_cassette",
    "first_live_seq",
    "import_cassette",
    "job_from_manifest",
    "rejudge_episode",
    "replay_agent_live",
    "replay_strict",
    "trajectory_from_cassette",
]

AGENT_LIVE_EPISODE = "ep_agent_live"


class CassetteManifest(BaseModel):
    """The header line: everything to rebuild `BuiltWorld`, the `Trajectory` and the episode
    pipeline offline. `agent_version` holds secret *names* only (never values)."""

    model_config = ConfigDict(extra="ignore")
    episode_id: str
    run_id: str
    scenario: Scenario
    world: WorldSpec
    rng_seed: int
    agent_version: AgentVersion
    persona: Persona
    rubrics: dict[str, Rubric] = {}
    platform_version: str = "0.0.0"
    exported_at: datetime = datetime(2026, 1, 1, tzinfo=UTC)


class CassetteError(ValueError):
    def __init__(self, message: str, line: int | None = None) -> None:
        super().__init__(f"line {line}: {message}" if line else message)
        self.line = line


class Divergence(BaseModel):
    seq: int
    expected: Any = None
    got: Any = None


class ReplayReport(BaseModel):
    identical: bool
    events: int
    divergence: Divergence | None = None


def export_cassette(
    snapshot: JournalSnapshot,
    manifest: CassetteManifest | Mapping[str, Any],
    *,
    secrets: Sequence[str] = (),
) -> str:
    """The cassette text. Every secret value is redacted over the whole text, a second line
    of defence behind the redaction at append time."""
    doc = (
        # exclude_none: a Matcher's *set* fields are its operators, so None must not be dumped
        manifest.model_dump(mode="json", exclude_none=True)
        if isinstance(manifest, CassetteManifest)
        else dict(manifest)
    )
    doc["exported_at"] = datetime.now(UTC).isoformat()
    text = dump_cassette(snapshot, doc)
    for value in secrets:
        if value:
            text = text.replace(value, "[REDACTED]")
    return text


def import_cassette(text: str) -> tuple[JournalSnapshot, CassetteManifest]:
    """Strict parse: the format string, every line against `Event` / `EffectRecord`, the
    manifest, and dense seqs. Raises `CassetteError` carrying the 1-based line number."""
    snap = JournalSnapshot()
    manifest: CassetteManifest | None = None
    for n, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
            kind = row.pop("t")
        except (ValueError, KeyError, AttributeError) as exc:
            raise CassetteError("not a cassette line (JSON object with a `t` field)", n) from exc
        try:
            if kind == "header":
                if row.get("format") != FORMAT:
                    raise CassetteError(f"unsupported format {row.get('format')!r}", n)
                try:
                    manifest = CassetteManifest.model_validate(row.get("manifest") or {})
                except ValidationError as exc:
                    err = exc.errors()[0]
                    where = ".".join(str(p) for p in err["loc"])
                    raise CassetteError(f"invalid manifest at {where}: {err['msg']}", n) from exc
            elif kind == "event":
                ev = Event.model_validate(row)
                if ev.seq != len(snap.events):
                    raise CassetteError(
                        f"event seq {ev.seq} is not {len(snap.events)} (not dense)", n
                    )
                snap.events.append(ev)
            elif kind == "effect":
                rec = EffectRecord.model_validate(row)
                snap.effects[rec.key] = rec
            else:
                raise CassetteError(f"unknown line type {kind!r}", n)
        except ValidationError as exc:
            raise CassetteError(f"invalid {kind}: {exc.errors()[0]['msg']}", n) from exc
    if manifest is None:
        raise CassetteError("cassette has no usable manifest header")
    return snap, manifest


def job_from_manifest(
    manifest: CassetteManifest,
    *,
    episode_id: str | None = None,
    agent_version: AgentVersion | None = None,
) -> EpisodeJob:
    return EpisodeJob(
        episode_id=episode_id or manifest.episode_id,
        run_id=manifest.run_id,
        scenario=manifest.scenario,
        world=manifest.world,
        agent_version=agent_version or manifest.agent_version,
        persona=manifest.persona,
        rubrics=dict(manifest.rubrics),
        rng_seed=manifest.rng_seed,
    )


def trajectory_from_cassette(snapshot: JournalSnapshot, manifest: CassetteManifest) -> Trajectory:
    built = build_world(manifest.world, manifest.scenario.world_overrides, manifest.rng_seed)
    return build_trajectory(manifest.episode_id, manifest.scenario, list(snapshot.events), built)


class StrictGateway:
    """A gateway that refuses every call: strict replay must not reach a model."""

    async def complete(self, role: str, *args: Any, **kwargs: Any) -> Any:
        raise NonDeterminism(f"strict replay made a live {role} call", expected=None, got=role)

    def estimate_usd_micros(self, *args: Any, **kwargs: Any) -> int:
        return 0

    async def embed(self, role: str, texts: list[str]) -> list[list[float]]:
        raise NonDeterminism("strict replay made a live embed call", expected=None, got=role)


async def replay_strict(cassette_text: str) -> ReplayReport:
    """In-process, no external calls. `identical` when the episode pipeline reproduces the
    recording event by event (kind, actor, payload); else the first difference."""
    snap, manifest = import_cassette(cassette_text)
    store = MemoryJournalStore()
    await store.append(
        manifest.episode_id, 0, events=snap.events, effects=list(snap.effects.values())
    )
    deps = RunnerDeps(store=store, gateway=StrictGateway())  # type: ignore[arg-type]
    try:
        await execute_episode(
            job_from_manifest(manifest), deps, replay_only=True, verify_payloads=True
        )
    except NonDeterminism as exc:
        seq = exc.seq if exc.seq is not None else len(snap.events)
        return ReplayReport(
            identical=False,
            events=len(snap.events),
            divergence=Divergence(
                seq=seq, expected=_jsonable(exc.expected), got=_jsonable(exc.got) or str(exc)
            ),
        )
    except PermanentEffectError as exc:  # a recorded failure re-raised outside the loop
        return ReplayReport(
            identical=False,
            events=len(snap.events),
            divergence=Divergence(seq=len(snap.events), expected=None, got=str(exc)),
        )
    return ReplayReport(identical=True, events=len(snap.events))


def _jsonable(value: object) -> Any:
    return None if value is None else json.loads(json.dumps(value, default=str))


async def replay_agent_live(
    cassette_text: str,
    agent_version: AgentVersion,
    deps: RunnerDeps,
    *,
    return_store: bool = False,
) -> Any:
    """Replay the recorded conversation against `agent_version`: the recording stands in for
    the simulator for as long as the agent's replies match, and everything after the first
    divergence runs live on `deps.gateway`. Returns the `EpisodeOutcome` (and the store when
    `return_store`, the new episode being `ep_agent_live`)."""
    snap, manifest = import_cassette(cassette_text)
    store = deps.store
    src = manifest.episode_id
    await store.append(src, 0, events=snap.events, effects=list(snap.effects.values()))
    await fork_for_agent_live(store, src, AGENT_LIVE_EPISODE)
    job = job_from_manifest(manifest, episode_id=AGENT_LIVE_EPISODE, agent_version=agent_version)
    out: EpisodeOutcome = await execute_episode(job, deps, mode="agent_live")
    return (out, store) if return_store else out


def first_live_seq(events: Sequence[Event]) -> int | None:
    """Where an agent_live episode left the recording (its `diverged` note), if it did."""
    for e in events:
        if e.kind == "sim_note" and e.payload.get("kind") == "diverged":
            return e.seq
    return None


# ------------------------------------------------------------------------------ rejudge


def apply_outcome_rule(
    checks: Collection[tuple[str, bool]], verdicts: Sequence[Verdict]
) -> Outcome:
    """The contracts' outcome rule for a scored episode: `failed` when the success check does
    not hold, a forbidden check holds, or any judge verdict is a hard-fail `fail`."""
    for check_id, holds in checks:
        if holds != (check_id == "success"):
            return "failed"
    if any(v.result == "fail" and v.hard_fail for v in verdicts):
        return "failed"
    return "passed"


async def rejudge_episode(
    trajectory: Trajectory,
    evaluators: Sequence[Rubric],
    gateway: Gateway,
    *,
    only: Collection[str] | None = None,
    policy_text: str = "",
    cache: Any = None,
) -> list[Verdict]:
    """Run the judge cascade again over a stored trajectory for the rubrics in `only` (all of
    `evaluators` when None). Touches no journal: the caller replaces the verdict rows."""
    chosen = [r for r in evaluators if only is None or r.id in only]
    evaluator = JudgeEvaluator(
        chosen,
        policy_text=policy_text,
        rule_stages=RULE_STAGE,
        context_provider=rule_context,
        cache=cache,
    )
    return await evaluator.evaluate(trajectory, gateway)
