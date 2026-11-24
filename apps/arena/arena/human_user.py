"""A `UserSimulator` backed by an input queue (CQ-P4). The text a person typed is the result of
a journaled effect of kind `human`, so a replay (or a resume) gets the same turns without
waiting for anyone."""

from __future__ import annotations

import asyncio

from gauntlet_core.engine import EpisodeCtx, SimTurn

__all__ = ["HumanUser"]


class HumanUser:
    def __init__(self, idle_s: float = 600.0) -> None:
        self._q: asyncio.Queue[str | None] = asyncio.Queue()
        self.idle_s = idle_s
        self.idle = asyncio.Event()  # set while the episode waits for the person

    def submit(self, text: str) -> None:
        self.idle.clear()
        self._q.put_nowait(text)

    def close(self) -> None:
        """The person left: the episode ends with `user_done` after the queued turns."""
        self._q.put_nowait(None)

    async def next_message(self, ctx: EpisodeCtx) -> SimTurn:
        n = sum(1 for e in ctx.trajectory_so_far if e.kind == "user_message")

        async def wait() -> tuple[dict[str, str | None], None]:
            self.idle.set()
            try:
                text = await asyncio.wait_for(self._q.get(), self.idle_s)
            except TimeoutError:
                text = None
            finally:
                self.idle.clear()
            return {"text": text}, None

        res = await ctx.effect("human", {"turn": n}, wait, retry_safe=True)
        text = res["text"]
        if text is None:
            return SimTurn("done", detail="human_left")
        return SimTurn("message", str(text))
