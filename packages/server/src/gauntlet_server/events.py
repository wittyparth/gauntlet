"""Run-scoped pub/sub (Redis) and the journal store wrapper that feeds the SSE stream.

Publishing is best effort: a failure is logged and swallowed, never fails an append."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any, Protocol

from gauntlet_core.engine import JournalSnapshot, JournalStore
from gauntlet_core.schema import EffectRecord, Event

__all__ = ["Publisher", "PublishingJournalStore", "RedisPublisher", "channel"]

log = logging.getLogger("gauntlet.events")


def channel(run_id: str) -> str:
    return f"gauntlet:run:{run_id}"


class Publisher(Protocol):
    async def publish(self, run_id: str, name: str, data: dict[str, Any]) -> None: ...


class RedisPublisher:
    def __init__(self, redis: Any) -> None:
        self._redis = redis

    async def publish(self, run_id: str, name: str, data: dict[str, Any]) -> None:
        try:
            await self._redis.publish(channel(run_id), json.dumps({"event": name, "data": data}))
        except Exception:
            log.warning("publish failed for run %s", run_id, exc_info=True)


class PublishingJournalStore:
    """Wraps a JournalStore for one episode; after a committed append it publishes an `event`
    message per event (no payload: REST is the truth) and a `verdict` message per verdict."""

    def __init__(self, inner: JournalStore, publisher: Publisher, run_id: str) -> None:
        self._inner, self._pub, self._run_id = inner, publisher, run_id

    async def load(self, episode_id: str) -> JournalSnapshot:
        return await self._inner.load(episode_id)

    async def append(
        self,
        episode_id: str,
        epoch: int,
        *,
        events: Sequence[Event] = (),
        effects: Sequence[EffectRecord] = (),
    ) -> None:
        await self._inner.append(episode_id, epoch, events=events, effects=effects)
        for e in events:
            head = {"episode_id": episode_id, "seq": e.seq, "kind": e.kind, "actor": e.actor}
            await self._pub.publish(self._run_id, "event", head)
            if e.kind == "verdict":
                p = e.payload
                await self._pub.publish(
                    self._run_id,
                    "verdict",
                    {
                        "episode_id": episode_id,
                        "evaluator": p.get("evaluator"),
                        "criterion": p.get("criterion"),
                        "result": p.get("result"),
                    },
                )

    async def abandon_attempt(self, episode_id: str, epoch: int) -> int:
        return await self._inner.abandon_attempt(episode_id, epoch)
