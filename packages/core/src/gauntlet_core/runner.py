"""The shared episode runner (CLI and worker). One episode = validate, build world, run the
loop, and in the finalizer run checks then the judge stage, all before `episode_ended`
(decision CQ-B13)."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx

from gauntlet_core.checks import evaluate_final
from gauntlet_core.engine import (
    BudgetLedger,
    EpisodeCtx,
    Finalizer,
    IndeterminateEffect,
    JournalStore,
    PermanentEffectError,
    Target,
    UserSimulator,
    run_episode,
)
from gauntlet_core.eval.rubrics import RULE_STAGE, rule_context
from gauntlet_core.judges import JudgeEvaluator
from gauntlet_core.llm import Gateway, llm_effect
from gauntlet_core.schema import (
    SCORED_OUTCOMES,
    AgentVersion,
    Cost,
    EventDraft,
    Json,
    LLMSimHandler,
    Outcome,
    Persona,
    Rubric,
    Scenario,
    Termination,
    ToolSpec,
    Verdict,
    WorldSpec,
)
from gauntlet_core.sim import LLMUserSimulator, ScriptedUserSimulator, make_guard, merge_persona
from gauntlet_core.targets import (
    Facade,
    HostedTarget,
    HttpTarget,
    OpenAICompatTarget,
    UrlPolicy,
)
from gauntlet_core.validate import contains_judge, validate_scenario
from gauntlet_core.world import BuiltWorld, World, build_trajectory, build_world

__all__ = [
    "MAX_ATTEMPTS",
    "EpisodeJob",
    "EpisodeOutcome",
    "RunnerDeps",
    "derive_episode_seed",
    "execute_episode",
    "execute_with_attempts",
    "make_finalizer",
    "make_llm_sim",
    "make_target",
]


# Attempts per episode before an indeterminate effect becomes platform_error. Every worker
# death in the middle of a wired turn burns one, so deployments that lose workers often (and
# the chaos test) raise it with GAUNTLET_MAX_ATTEMPTS.
MAX_ATTEMPTS = int(os.environ.get("GAUNTLET_MAX_ATTEMPTS") or 3)


_TURNS_TAG = "attack_turns"  # = gauntlet_core.security.placement.TURNS_TAG (no import cycle)


@dataclass
class EpisodeJob:
    episode_id: str
    run_id: str
    scenario: Scenario
    world: WorldSpec
    agent_version: AgentVersion
    persona: Persona
    rubrics: dict[str, Rubric]
    rng_seed: int
    secrets: dict[str, str] = field(default_factory=dict)


@dataclass
class RunnerDeps:
    store: JournalStore
    gateway: Gateway
    budget: BudgetLedger | None = None
    http: httpx.AsyncClient | None = None
    url_policy: UrlPolicy = field(default_factory=lambda: UrlPolicy(allow_private=False))
    facade: Facade | None = None
    judge_enabled: bool = True
    on_event: Callable[[str, dict[str, Any]], None] | None = None


@dataclass
class EpisodeOutcome:
    outcome: Outcome
    termination: Termination
    detail: str | None
    cost: Cost
    reasons: tuple[str, ...]
    verdicts: list[Verdict]
    world_fidelity: str
    latency_ms: int


def derive_episode_seed(seed: int, scenario_id: str, rep: int) -> int:
    digest = hashlib.sha256(f"{seed}:{scenario_id}:{rep}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % (2**63)


def make_target(
    agent_version: AgentVersion,
    world: World,
    built: BuiltWorld,
    deps: RunnerDeps,
    secrets: Mapping[str, str],
) -> Target:
    cfg = agent_version.target
    if cfg.kind == "hosted":
        return HostedTarget(cfg, world, deps.gateway)
    client = deps.http or httpx.AsyncClient()
    facade = deps.facade if cfg.wired else None
    if cfg.kind == "openai_compat":
        return OpenAICompatTarget(
            cfg, secrets=secrets, client=client, safety=deps.url_policy, facade=facade
        )
    return HttpTarget(cfg, secrets=secrets, client=client, safety=deps.url_policy, facade=facade)


def make_finalizer(
    scenario: Scenario,
    built: BuiltWorld,
    *,
    gateway: Gateway | None = None,
    rubrics: Mapping[str, Rubric] | None = None,
    policy_text: str = "",
    judge_enabled: bool = True,
) -> Finalizer:
    """Checks first, then (when enabled) the judge stage, as effects on the same ctx."""

    async def finalize(ctx: EpisodeCtx, termination: Termination) -> Outcome:
        traj = build_trajectory(ctx.episode_id, scenario, list(ctx.trajectory_so_far), built)
        named = [
            ("success", None, scenario.success),
            *[(n.id, n.severity, n.check) for n in scenario.forbidden],
        ]
        outcome: Outcome = "passed"
        for check_id, severity, check in named:
            if contains_judge(check):
                raise PermanentEffectError("judge_check_unsupported", check_id)
            res = evaluate_final(check, traj)
            await ctx.emit(
                EventDraft(
                    kind="check_result",
                    actor="platform",
                    sim_time=ctx.now(),
                    payload={
                        "check_id": check_id,
                        "holds": res.holds,
                        "severity": severity,
                        "evidence": [e.model_dump(mode="json") for e in res.evidence],
                    },
                )
            )
            if res.holds != (check_id == "success"):
                outcome = "failed"
        if judge_enabled and gateway is not None and rubrics and outcome in SCORED_OUTCOMES:
            evaluator = JudgeEvaluator(
                list(rubrics.values()),
                ctx=ctx,
                policy_text=policy_text,
                rule_stages=RULE_STAGE,
                context_provider=rule_context,
            )
            for v in await evaluator.evaluate(traj, gateway):
                await ctx.emit(
                    EventDraft(
                        kind="verdict",
                        actor="platform",
                        sim_time=ctx.now(),
                        payload=v.model_dump(mode="json"),
                    )
                )
                if v.result == "fail" and v.hard_fail:
                    outcome = "failed"
        return outcome

    return finalize


def make_llm_sim(gateway: Gateway):
    async def sim(ctx: EpisodeCtx, spec: ToolSpec, args: Json) -> Any:
        assert isinstance(spec.handler, LLMSimHandler)
        messages: list[Json] = [
            {
                "role": "system",
                "content": "You simulate a backend tool. Reply with JSON only. "
                + spec.handler.instructions,
            },
            {"role": "user", "content": json.dumps(args, default=str)},
        ]
        # Nested inside the `tool` effect (1.7a): its own `llm` effect records cost and result.
        res = await llm_effect(
            ctx, gateway, "simulator", messages, temperature=0.0, seed=ctx.rng_seed
        )
        try:
            return json.loads(res.text)
        except ValueError:
            return res.text

    return sim


def _facts(ctx: EpisodeCtx, world: World) -> tuple[tuple[str, ...], list[Verdict], int, str]:
    reasons: list[str] = []
    verdicts: list[Verdict] = []
    latency = 0
    sim_tools = {n for n, t in world.built.tools.items() if isinstance(t.handler, LLMSimHandler)}
    fidelity = "full"
    for e in ctx.trajectory_so_far:
        if e.kind in ("agent_message", "tool_result"):  # agent-side time, not the simulator's
            latency += e.wall_ms
        if e.kind == "check_result":
            p = e.payload
            if p["holds"] != (p["check_id"] == "success"):
                reasons.append(p["check_id"])
        elif e.kind == "verdict":
            verdicts.append(Verdict.model_validate(e.payload))
        elif e.kind == "tool_call" and e.payload.get("tool") in sim_tools:
            fidelity = "simulated"
    return tuple(reasons), verdicts, latency, fidelity


async def _total_cost(store: JournalStore, episode_id: str) -> Cost:
    total = Cost()
    for rec in (await store.load(episode_id)).effects.values():
        if rec.cost is not None:
            total = total + rec.cost
    return total


async def execute_episode(
    job: EpisodeJob,
    deps: RunnerDeps,
    *,
    epoch: int = 0,
    replay_only: bool = False,
    sim: UserSimulator | None = None,
) -> EpisodeOutcome:
    """Run, resume or replay one episode. Raises StaleLease, IndeterminateEffect and
    NonDeterminism to the caller."""
    scn = job.scenario
    ctx = await EpisodeCtx.open(
        deps.store,
        job.episode_id,
        epoch=epoch,
        run_id=job.run_id,
        rng_seed=job.rng_seed,
        budget=deps.budget,
        secrets=tuple(job.secrets.values()),
        replay_only=replay_only,
        clock_start=job.world.clock_start,
    )
    if deps.on_event:
        deps.on_event("episode_started", {"episode_id": job.episode_id})

    issues = validate_scenario(scn, job.world, rubric_ids=set(job.rubrics) | set(scn.rubrics))
    if issues:
        detail = "; ".join(str(i) for i in issues)
        for kind, payload in (
            ("episode_started", {"scenario": scn.id, "version": scn.version}),
            (
                "episode_ended",
                {"outcome": "invalid_scenario", "termination": "error", "detail": detail},
            ),
        ):
            await ctx.emit(
                EventDraft(kind=kind, actor="platform", sim_time=ctx.now(), payload=payload)  # type: ignore[arg-type]
            )
        await ctx.flush()
        out = EpisodeOutcome("invalid_scenario", "error", detail, Cost(), (), [], "full", 0)
        if deps.on_event:
            deps.on_event(
                "episode_finished", {"episode_id": job.episode_id, "outcome": out.outcome}
            )
        return out

    built = build_world(job.world, scn.world_overrides, job.rng_seed)
    world = World(built, llm_sim=make_llm_sim(deps.gateway))
    world.bind(ctx)
    persona = merge_persona(job.persona, scn.persona_overrides)
    target = make_target(job.agent_version, world, built, deps, job.secrets)
    if sim is None and _TURNS_TAG in scn.tags:  # placed user_turn attack: scripted turns
        sim = ScriptedUserSimulator(json.loads(scn.tags[_TURNS_TAG]))
    sim = sim or LLMUserSimulator(scn, persona, deps.gateway, guard=make_guard(scn, persona))
    finalizer = make_finalizer(
        scn,
        built,
        gateway=deps.gateway,
        rubrics=job.rubrics,
        policy_text=job.agent_version.profile.policies_text,
        judge_enabled=deps.judge_enabled,
    )
    result = await run_episode(ctx, scn, target, sim, finalize=finalizer)
    reasons, verdicts, latency, fidelity = _facts(ctx, world)
    out = EpisodeOutcome(
        result.outcome,
        result.termination,
        result.detail,
        await _total_cost(deps.store, job.episode_id),
        reasons,
        verdicts,
        fidelity,
        latency,
    )
    if deps.on_event:
        deps.on_event("episode_finished", {"episode_id": job.episode_id, "outcome": out.outcome})
    return out


async def _end_as_platform_error(
    job: EpisodeJob, deps: RunnerDeps, epoch: int, detail: str
) -> EpisodeOutcome:
    ctx = await EpisodeCtx.open(
        deps.store,
        job.episode_id,
        epoch=epoch,
        run_id=job.run_id,
        rng_seed=job.rng_seed,
        clock_start=job.world.clock_start,
    )
    ctx.seek_end()
    await ctx.emit(
        EventDraft(
            kind="episode_ended",
            actor="platform",
            sim_time=ctx.now(),
            payload={"outcome": "platform_error", "termination": "error", "detail": detail},
        )
    )
    await ctx.flush()
    out = EpisodeOutcome(
        "platform_error", "error", detail, await _total_cost(deps.store, job.episode_id),
        (), [], "full", 0,
    )  # fmt: skip
    if deps.on_event:
        deps.on_event("episode_finished", {"episode_id": job.episode_id, "outcome": out.outcome})
    return out


async def execute_with_attempts(
    job: EpisodeJob,
    deps: RunnerDeps,
    *,
    epoch: int = 0,
    replay_only: bool = False,
    sim: UserSimulator | None = None,
) -> EpisodeOutcome:
    """`execute_episode` plus the abandon-attempt path (hard-cores 1.3 and 1.7a): when resuming
    meets an indeterminate effect the journal is archived under its attempt number and the
    episode restarts from scratch; the third indeterminate attempt ends as `platform_error`.
    Raises StaleLease and NonDeterminism to the caller."""
    while True:
        try:
            extra = {"sim": sim} if sim is not None else {}
            return await execute_episode(job, deps, epoch=epoch, replay_only=replay_only, **extra)
        except IndeterminateEffect as exc:
            if replay_only:
                raise
            attempt = (await deps.store.load(job.episode_id)).attempt
            if attempt + 1 >= MAX_ATTEMPTS:
                detail = f"IndeterminateEffect in all {MAX_ATTEMPTS} attempts: {exc}"
                return await _end_as_platform_error(job, deps, epoch, detail)
            await deps.store.abandon_attempt(job.episode_id, epoch)
