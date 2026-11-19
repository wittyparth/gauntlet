"""LLM-driven user simulator."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from gauntlet_core.engine import EpisodeCtx, PermanentEffectError, SimTurn
from gauntlet_core.judges import SimulatorGuard
from gauntlet_core.llm import Gateway, structured_effect
from gauntlet_core.schema import EventDraft, Persona, Scenario

from .persona import merge_persona
from .prompt import (
    RE_ASK_NUDGE,
    SimOutput,
    build_messages,
    build_system_prompt,
    lenient_sim_output,
)
from .typos import apply_typos

__all__ = ["GuardHit", "LLMUserSimulator", "SimGuard", "make_guard"]


@dataclass(frozen=True)
class GuardHit:
    """`drift` ends the episode as `simulator_error`; `note` is recorded as a `sim_note`
    event and the episode continues."""

    kind: str  # "drift" | "note"
    code: str
    detail: str

    def text(self) -> str:
        return f"{self.code}: {self.detail}"


SimGuard = Callable[[EpisodeCtx, SimOutput], GuardHit | None]


def make_guard(scenario: Scenario, persona: Persona) -> SimGuard:
    """Adapt `gauntlet_core.judges.SimulatorGuard` to the simulator hook. Genuine drift (language
    switch, speaking as the assistant, empty) ends the episode; `hidden_fact_early` only notes."""
    language = persona.traits.get("language")
    guard = SimulatorGuard(
        hidden_facts=scenario.hidden_facts,
        persona_language=language if isinstance(language, str) else None,
    )

    def check(ctx: EpisodeCtx, out: SimOutput) -> GuardHit | None:
        agent = [
            e.payload.get("text", "") for e in ctx.trajectory_so_far if e.kind == "agent_message"
        ]
        issue = guard.check(out.message, agent)
        return GuardHit(issue.kind, issue.code, issue.detail) if issue else None

    return check


class LLMUserSimulator:
    def __init__(
        self,
        scenario: Scenario,
        persona: Persona,
        gateway: Gateway,
        *,
        role: str = "simulator",
        guard: SimGuard | None = None,
    ) -> None:
        self.scenario = scenario
        self.persona = merge_persona(persona, scenario.persona_overrides)
        self.gateway, self.role, self.guard = gateway, role, guard
        self._system = build_system_prompt(scenario, self.persona)

    async def _ask(self, ctx: EpisodeCtx, turn: int, nudge: str | None) -> SimOutput | SimTurn:
        try:
            res = await structured_effect(
                ctx,
                self.gateway,
                self.role,
                build_messages(self._system, ctx, nudge=nudge),
                response_model=SimOutput,
                lenient=lenient_sim_output,
                temperature=0.7,
                seed=ctx.rng_seed + turn,
                error_cls=PermanentEffectError,
            )
        except PermanentEffectError as e:  # BudgetExhausted is not one: it propagates
            return SimTurn("drift", detail=f"simulator_llm_error:{e.code}")
        if not isinstance(res.parsed, SimOutput):
            return SimTurn("drift", detail="simulator_llm_error:no_structured_output")
        return res.parsed

    async def next_message(self, ctx: EpisodeCtx) -> SimTurn:
        turn = sum(1 for e in ctx.trajectory_so_far if e.kind == "user_message")
        if turn == 0 and self.scenario.opening_message is not None:
            return SimTurn("message", self.scenario.opening_message)
        spoke_to = any(e.kind == "agent_message" for e in ctx.trajectory_so_far)

        out = await self._ask(ctx, turn, None)
        if isinstance(out, SimTurn):
            return out
        if out.is_done() and not spoke_to:  # cannot be finished before the first reply
            out = await self._ask(ctx, turn, RE_ASK_NUDGE)
            if isinstance(out, SimTurn):
                return out
            if out.is_done():
                return SimTurn("done", detail="done_before_reply")
        if out.is_done():
            return SimTurn("done", detail=out.done_reason or "")
        if not out.message.strip():
            return SimTurn("drift", detail="empty_message")
        if self.guard is not None and (hit := self.guard(ctx, out)) is not None:
            if hit.kind == "drift":
                return SimTurn("drift", detail=hit.text())
            await ctx.emit(
                EventDraft(
                    kind="sim_note",
                    actor="platform",
                    sim_time=ctx.now(),
                    payload={"note": hit.detail, "kind": hit.code},
                )
            )
        text = out.message
        rate = self.persona.traits.get("typo_rate")
        if isinstance(rate, int | float) and rate > 0:
            text = apply_typos(text, float(rate), ctx.random)
        return SimTurn("message", text)
