"""A user simulator that needs no model: fixed turns, for tests and the DVA."""

from __future__ import annotations

from typing import Literal

from gauntlet_core.engine import EpisodeCtx, SimTurn

__all__ = ["ScriptedUserSimulator"]


class ScriptedUserSimulator:
    def __init__(self, turns: list[str], *, then: Literal["done", "repeat_last"] = "done") -> None:
        self.turns, self.then = list(turns), then

    async def next_message(self, ctx: EpisodeCtx) -> SimTurn:
        n = sum(1 for e in ctx.trajectory_so_far if e.kind == "user_message")
        if n < len(self.turns):
            return SimTurn("message", self.turns[n])
        if self.then == "repeat_last" and self.turns:
            return SimTurn("message", self.turns[-1])
        return SimTurn("done", detail="script_finished")
