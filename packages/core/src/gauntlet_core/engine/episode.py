"""The episode loop (docs/plan/03-hard-cores.md section 1.7).

The loop is deliberately dumb: it alternates simulator and target turns and decides when to
stop. Scoring is injected (`finalize`), so the engine does not depend on checks or judges.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from gauntlet_core.schema import Cost, EventDraft, Origin, Outcome, Scenario, Termination

from .ctx import EpisodeCtx
from .errors import BudgetExhausted, EngineError, PermanentEffectError, TargetError


@dataclass(frozen=True)
class SimTurn:
    kind: Literal["message", "done", "drift"]
    text: str = ""
    detail: str = ""


class UserSimulator(Protocol):
    async def next_message(self, ctx: EpisodeCtx) -> SimTurn: ...


class Target(Protocol):
    stateful: bool

    async def open(self, ctx: EpisodeCtx) -> None: ...

    async def send(self, ctx: EpisodeCtx, user_text: str) -> str: ...

    async def close(self, ctx: EpisodeCtx) -> None: ...


Finalizer = Callable[[EpisodeCtx, Termination], Awaitable[Outcome]]


@dataclass(frozen=True)
class EpisodeResult:
    outcome: Outcome
    termination: Termination
    detail: str | None
    turns: int
    cost: Cost
    live_effects: int


async def _passed(ctx: EpisodeCtx, termination: Termination) -> Outcome:
    return "passed"


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def agent_stuck(ctx: EpisodeCtx, repeats: int = 3) -> bool:
    """The agent has sent the same reply `repeats` times in a row."""
    replies = [
        e.payload.get("text", "") for e in ctx.trajectory_so_far if e.kind == "agent_message"
    ]
    if len(replies) < repeats:
        return False
    tail = {_norm(t) for t in replies[-repeats:]}
    return len(tail) == 1 and tail != {""}


async def run_episode(
    ctx: EpisodeCtx,
    scenario: Scenario,
    target: Target,
    sim: UserSimulator,
    *,
    finalize: Finalizer = _passed,
) -> EpisodeResult:
    """Run (or resume, or replay) one episode. Safe to call again over the same journal.

    Raises StaleLease, IndeterminateEffect and NonDeterminism to the runner; every other
    ending is recorded as an `episode_ended` event and returned.
    """

    async def end(
        outcome: Outcome | None, termination: Termination, detail: str | None = None
    ) -> EpisodeResult:
        try:
            await target.close(ctx)
        except EngineError:
            raise
        except Exception:  # closing is best-effort and must not mask the real ending
            pass
        final = outcome if outcome is not None else await finalize(ctx, termination)
        await ctx.emit(
            EventDraft(
                kind="episode_ended",
                actor="platform",
                sim_time=ctx.now(),
                payload={"outcome": final, "termination": termination, "detail": detail},
            )
        )
        await ctx.flush()
        return EpisodeResult(final, termination, detail, ctx.turn, ctx.spent, ctx.live_effects)

    await ctx.emit(
        EventDraft(
            kind="episode_started",
            actor="platform",
            sim_time=ctx.now(),
            payload={"scenario": scenario.id, "version": scenario.version},
        )
    )
    try:
        await target.open(ctx)
        while True:
            turn = await sim.next_message(ctx)
            if turn.kind == "drift":
                return await end("simulator_error", "simulator_drift", turn.detail)
            if turn.kind == "done":
                return await end(None, "user_done", turn.detail or None)
            await ctx.emit(
                EventDraft(
                    kind="user_message",
                    actor="user",
                    sim_time=ctx.now(),
                    wall_ms=ctx.last_effect_ms,
                    payload={"text": turn.text},
                    origin=Origin(trust="user"),
                )
            )
            reply = await target.send(ctx, turn.text)
            await ctx.emit(
                EventDraft(
                    kind="agent_message",
                    actor="agent",
                    sim_time=ctx.now(),
                    wall_ms=ctx.last_effect_ms,
                    payload={"text": reply},
                )
            )
            ctx.turn += 1
            if agent_stuck(ctx):
                return await end(None, "agent_stuck")
            if ctx.turn >= scenario.max_turns:
                return await end(None, "max_turns")
    except BudgetExhausted:
        return await end("budget_exhausted", "budget")
    except TargetError as exc:
        return await end("target_error", "target_unreachable", str(exc))
    except PermanentEffectError as exc:
        return await end("platform_error", "error", str(exc))
