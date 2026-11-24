"""The arena's target: Pip, a small support agent whose tools are the arena world, whose model is
an injected `Gateway`, and whose every step passes the gateway of the level (if it has one)."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from gauntlet_core.engine import EpisodeCtx
from gauntlet_core.gateway import Guard, Session
from gauntlet_core.llm import Gateway
from gauntlet_core.llm.effects import llm_effect
from gauntlet_core.schema import EventDraft, Json, PlantedCanary
from gauntlet_core.world.markers import scan_markers
from gauntlet_core.world.world import World

from .flags import leaked
from .levels import SYSTEM_PROMPT, Level
from .scan import scan_output

__all__ = ["ArenaAgent", "ArenaState"]

MAX_STEPS = 4
MAX_TOOL_CALLS = 2
REFUSAL = "I am sorry, I cannot share that."


@dataclass
class ArenaState:
    """What the service reads after a turn."""

    replies: list[str] = field(default_factory=list)
    tokens: int = 0
    scanned: int = 0
    filtered: int = 0


class ArenaAgent:
    stateful = False

    def __init__(
        self,
        *,
        level: Level,
        world: World,
        brain: Gateway,
        guard: Guard | None,
        canary: str,
        filter_canary: PlantedCanary | None,
        state: ArenaState,
        on_reply: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self.level, self.world, self.brain, self.guard = level, world, brain, guard
        self.canary, self.filter_canary, self.state = canary, filter_canary, state
        self.on_reply = on_reply
        self.session: Session | None = None
        self.history: list[Json] = []

    async def open(self, ctx: EpisodeCtx) -> None:
        self.world.bind(ctx)
        self.session = self.guard.session(ctx.episode_id) if self.guard else None
        self.history = [{"role": "system", "content": SYSTEM_PROMPT.format(canary=self.canary)}]

    async def close(self, ctx: EpisodeCtx) -> None:
        return None

    async def send(self, ctx: EpisodeCtx, user_text: str) -> str:
        sess = self.session
        if sess:
            await sess.record_user_message(user_text)
        self.history.append({"role": "user", "content": user_text})
        tools = self.world.tool_schemas()
        text = ""
        for _ in range(MAX_STEPS):
            res = await llm_effect(
                ctx, self.brain, "simulator", list(self.history), tools=tools, temperature=0.0
            )
            self.state.tokens += res.cost.input_tokens + res.cost.output_tokens
            if not res.tool_calls:
                text = res.text
                break
            self.history.append(
                {
                    "role": "assistant",
                    "content": res.text,
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                        }
                        for c in res.tool_calls
                    ],
                }
            )
            for call in res.tool_calls[:MAX_TOOL_CALLS]:
                self.history.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": await self._tool(ctx, call.id, call.name, call.arguments),
                    }
                )
        else:
            text = "I could not finish that request."
        return await self._deliver(ctx, text)

    async def _tool(self, ctx: EpisodeCtx, call_id: str, name: str, args: Json) -> str:
        sess = self.session
        if sess:
            decision = await sess.check_tool_call(name, args, call_id=call_id)
            if decision.action == "block":
                await ctx.emit(
                    EventDraft(
                        kind="sim_note",
                        actor="platform",
                        sim_time=ctx.now(),
                        payload={
                            "note": "policy_block",
                            "tool": name,
                            "rule": decision.rule_id,
                            "call_id": call_id,
                        },
                    )
                )
                return json.dumps({"error": "blocked_by_policy", "message": decision.message})
        tr = await self.world.call_tool(ctx, name, args, via="wired")
        out: Any = tr.result if tr.ok else {"error": tr.error}
        spec = self.world.built.tools.get(name)
        if sess:
            await sess.record_tool_result(
                call_id,
                name,
                out,
                untrusted=bool(spec and spec.untrusted_output) or None,
                ok=tr.ok,
                markers=scan_markers(out),
            )
        return json.dumps(out, default=str)

    async def _deliver(self, ctx: EpisodeCtx, text: str) -> str:
        sess = self.session
        if sess:
            decision = await sess.check_output(text)
            if decision.action == "block":
                text = decision.message or REFUSAL
            elif decision.modified and "text" in decision.modified:
                text = str(decision.modified["text"])
        if self.filter_canary is not None and leaked(text, self.filter_canary):
            self.state.filtered += 1
            text = REFUSAL
        text, masked = scan_output(text)
        self.state.scanned += masked
        if (
            self.state.replies and text == self.state.replies[-1]
        ):  # the engine ends a conversation after 3 repeats
            text = f"{text} (turn {ctx.turn + 1})"
        self.history.append({"role": "assistant", "content": text})
        self.state.replies.append(text)
        if self.on_reply:
            await self.on_reply(text)
        return text
