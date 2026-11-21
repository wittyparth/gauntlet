"""The mock world behind the guard (P4-5): policy enforcement inside simulated episodes.

`GuardedWorld(world, session)` has the `World` interface. Every tool call is checked first. A
blocked call is journaled as the call plus a failed result (and a `policy_block` note) and
never reaches the tool, so no effect is recorded; the call counters still advance exactly as an
executed call would, which keeps resume and strict replay aligned (the decision is pure given
the prefix). Approvals in simulation are an auto-deny unless `approve_all` is set.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from gauntlet_core.engine import EpisodeCtx
from gauntlet_core.schema import Event, EventDraft, Json, Origin, Policy, WorldSnapshot
from gauntlet_core.world import BuiltWorld, World
from gauntlet_core.world.world import ToolResult

from .approvals import CallbackApprovals
from .guard import Guard
from .session import Session
from .sinks import MemorySink

__all__ = ["GuardedWorld", "guard_for_episode"]


def guard_for_episode(
    policy: Policy,
    ctx: EpisodeCtx,
    *,
    mode: str | None = None,
    approve_all: bool = False,
) -> tuple[Guard, MemorySink]:
    """A fresh guard whose clock is the episode's simulated time and whose records stay in
    memory. `mode="enforce"` overrides the stored mode (verification runs)."""
    sink = MemorySink()

    def clock() -> datetime:
        return ctx.now()

    approvals = CallbackApprovals(lambda decision, record: "approved" if approve_all else "denied")
    guard = Guard(
        policy,
        mode=mode,  # type: ignore[arg-type]
        sink=sink,
        approvals=approvals,
        clock=clock,
    )
    return guard, sink


class GuardedWorld(World):
    def __init__(self, world: World, session: Session) -> None:
        # Deliberately not calling World.__init__: all state lives in the wrapped world.
        self._inner = world
        self.session = session

    # -- delegated state --------------------------------------------------------------------

    @property
    def built(self) -> BuiltWorld:  # type: ignore[override]
        return self._inner.built

    @property
    def state(self):  # type: ignore[no-untyped-def,override]
        return self._inner.state

    def bind(self, ctx: EpisodeCtx) -> None:
        self._inner.bind(ctx)

    def apply_events(self, events: Sequence[Event]) -> None:
        self._inner.apply_events(events)

    def snapshot(self) -> WorldSnapshot:
        return self._inner.snapshot()

    def tool_schemas(self, subset: list[str] | None = None) -> list[Json]:
        return self._inner.tool_schemas(subset)

    # -- the guarded call -------------------------------------------------------------------

    async def call_tool(
        self, ctx: EpisodeCtx, tool: str, args: Json, *, via: str = "hosted"
    ) -> ToolResult:
        inner = self._inner
        ctx.add_replay_hook(inner.apply_events)
        call_id = f"call_{inner._n}"  # pyright: ignore[reportPrivateUsage]
        decision = await self.session.check_tool_call(tool, args, call_id=call_id)
        if decision.action == "block":
            return await self._blocked(ctx, call_id, tool, args, via, decision)
        if decision.modified and isinstance(decision.modified.get("args"), dict):
            args = decision.modified["args"]  # redact: the call goes ahead rewritten
        res = await inner.call_tool(ctx, tool, args, via=via)
        spec = inner.built.tools.get(tool)
        await self.session.record_tool_result(
            res.call_id,
            tool,
            res.result if res.ok else {"error": res.error},
            untrusted=bool(spec and spec.untrusted_output),
            ok=res.ok,
        )
        return res

    async def _blocked(
        self, ctx: EpisodeCtx, call_id: str, tool: str, args: Json, via: str, decision: Any
    ) -> ToolResult:
        inner = self._inner
        inner._n += 1  # pyright: ignore[reportPrivateUsage]
        inner._calls[tool] += 1  # pyright: ignore[reportPrivateUsage]
        message = decision.message or decision.rule_id or "policy"
        error = f"blocked_by_policy: {message}"
        await ctx.emit(
            EventDraft(
                kind="tool_call",
                actor="agent",
                sim_time=ctx.now(),
                payload={"call_id": call_id, "tool": tool, "args": args, "via": via},
            )
        )
        await ctx.emit(
            EventDraft(
                kind="sim_note",
                actor="platform",
                sim_time=ctx.now(),
                payload={
                    "note": "policy_block",
                    "rule_id": decision.rule_id,
                    "action": decision.action,
                    "kind": "guard",
                    "call_id": call_id,
                },
            )
        )
        await ctx.emit(
            EventDraft(
                kind="tool_result",
                actor="tool",
                sim_time=ctx.now(),
                payload={
                    "call_id": call_id,
                    "ok": False,
                    "result": None,
                    "patch": [],
                    "error": error,
                },
                origin=Origin(trust="system", source=tool),
            )
        )
        return ToolResult(call_id, False, None, error)
