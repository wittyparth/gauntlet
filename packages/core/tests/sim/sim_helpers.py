"""Builders for simulator tests."""

from __future__ import annotations

from gauntlet_core.engine import EpisodeCtx
from gauntlet_core.llm import FakeReply
from gauntlet_core.schema import Persona, Scenario


def scenario(max_turns: int = 6, **kw) -> Scenario:
    base = {
        "id": "scn",
        "title": "t",
        "goal": "get a refund for order 1001",
        "persona": "per_cooperative",
        "world": "w",
        "max_turns": max_turns,
        "success": {"type": "output", "matcher": {"contains": "x"}},
    }
    return Scenario.model_validate({**base, **kw})


def persona(**kw) -> Persona:
    base = {
        "id": "per_x",
        "name": "Sam",
        "description": "Friendly.",
        "traits": {"verbosity": "low"},
        "behavior_rules": ["be brief"],
    }
    return Persona.model_validate({**base, **kw})


def say(message: str, note: str = "wants refund") -> FakeReply:
    return FakeReply(parsed={"state_note": note, "action": "say", "message": message})


def done(reason: str = "goal_met") -> FakeReply:
    return FakeReply(
        parsed={"state_note": "finished", "action": "done", "message": "", "done_reason": reason}
    )


class EchoTarget:
    stateful = False

    def __init__(self, replies: list[str] | None = None) -> None:
        self.replies = replies

    async def open(self, ctx: EpisodeCtx) -> None:
        return None

    async def close(self, ctx: EpisodeCtx) -> None:
        return None

    async def send(self, ctx: EpisodeCtx, user_text: str) -> str:
        n = sum(1 for e in ctx.trajectory_so_far if e.kind == "agent_message")
        if self.replies is not None:
            return self.replies[min(n, len(self.replies) - 1)]
        return f"echo {n}: {user_text}"
