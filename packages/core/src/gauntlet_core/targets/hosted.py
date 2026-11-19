"""Hosted target: Gauntlet runs the agent itself (system prompt, model, tool loop over the
mock world). Replay is free: the same calls re-execute over recorded `llm` and `tool` effects."""

from __future__ import annotations

import json

from gauntlet_core.engine import EpisodeCtx
from gauntlet_core.llm import Gateway, LLMResult, llm_effect
from gauntlet_core.schema import HostedTargetConfig, Json
from gauntlet_core.world import World

from .errors import TargetError

__all__ = ["HostedTarget"]


def _assistant_message(res: LLMResult) -> Json:
    return {
        "role": "assistant",
        "content": res.text or None,
        "tool_calls": [
            {
                "id": t.id,
                "type": "function",
                "function": {"name": t.name, "arguments": json.dumps(t.arguments)},
            }
            for t in res.tool_calls
        ],
    }


class HostedTarget:
    stateful = False

    def __init__(
        self,
        config: HostedTargetConfig,
        world: World,
        gateway: Gateway,
        *,
        max_tool_rounds: int = 8,
    ) -> None:
        self.config, self.world, self.gateway = config, world, gateway
        self.max_tool_rounds = max_tool_rounds
        self._history: list[Json] = []
        self._tools = world.tool_schemas(config.tools)
        self._allowed = {t["function"]["name"] for t in self._tools}

    async def open(self, ctx: EpisodeCtx) -> None:
        system = self.config.system_prompt
        context = self.world.built.system_context
        if context:
            system += "\n\n" + "\n".join(context)
        self._history = [{"role": "system", "content": system}]

    async def close(self, ctx: EpisodeCtx) -> None:
        return None

    async def _call(self, ctx: EpisodeCtx, *, tools: bool) -> LLMResult:
        return await llm_effect(
            ctx,
            self.gateway,
            f"model:{self.config.model}",
            [dict(m) for m in self._history],
            tools=self._tools or None if tools else None,
            temperature=self.config.temperature,
            seed=ctx.rng_seed,
            error_cls=TargetError,
        )

    async def send(self, ctx: EpisodeCtx, user_text: str) -> str:
        self._history.append({"role": "user", "content": user_text})
        for _ in range(self.max_tool_rounds):
            res = await self._call(ctx, tools=True)
            self._history.append(_assistant_message(res))
            if not res.tool_calls:
                return res.text
            for call in res.tool_calls:
                if call.name not in self._allowed:
                    content = json.dumps({"error": "unknown_tool"})
                else:
                    args = call.arguments if isinstance(call.arguments, dict) else {}
                    out = await self.world.call_tool(ctx, call.name, args, via="hosted")
                    content = out.as_text()
                self._history.append({"role": "tool", "tool_call_id": call.id, "content": content})
        res = await self._call(ctx, tools=False)  # tool budget spent: force a text answer
        self._history.append({"role": "assistant", "content": res.text})
        return res.text
