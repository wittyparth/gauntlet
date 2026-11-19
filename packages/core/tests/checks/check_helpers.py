"""Builders shared by the checks tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from gauntlet_core.schema import (
    Check,
    Event,
    Origin,
    PatchOp,
    Scenario,
    Trajectory,
)
from pydantic import TypeAdapter

T0 = datetime(2026, 1, 1, tzinfo=UTC)
CHECK = TypeAdapter(Check)


def chk(d: dict[str, Any]) -> Any:
    return CHECK.validate_python(d)


def scenario() -> Scenario:
    return Scenario.model_validate(
        {
            "id": "scn",
            "title": "t",
            "goal": "g",
            "persona": "p",
            "world": "w",
            "max_turns": 5,
            "success": {"type": "output", "matcher": {"contains": "x"}},
        }
    )


class Tb:
    """Fluent trajectory builder. Events get consecutive seqs from 1."""

    def __init__(self) -> None:
        self.events: list[Event] = []
        self.n = 0

    def _add(self, kind: str, actor: str, payload: dict[str, Any], origin: Origin | None = None):
        self.n += 1
        self.events.append(
            Event(
                seq=self.n,
                kind=kind,  # type: ignore[arg-type]
                actor=actor,  # type: ignore[arg-type]
                sim_time=T0 + timedelta(seconds=self.n),
                payload=payload,
                origin=origin,
            )
        )
        return self

    def user(self, text: str):
        return self._add("user_message", "user", {"text": text})

    def agent(self, text: str):
        return self._add("agent_message", "agent", {"text": text})

    def call(
        self,
        tool: str,
        args: dict[str, Any] | None = None,
        *,
        ok: bool | None = True,
        result: Any = None,
        patch: list[PatchOp] | None = None,
        markers: list[str] | None = None,
    ):
        cid = f"c{self.n}"
        self._add("tool_call", "agent", {"call_id": cid, "tool": tool, "args": args or {}})
        if ok is not None:
            origin = Origin(trust="untrusted_external", markers=markers) if markers else None
            self._add(
                "tool_result",
                "tool",
                {
                    "call_id": cid,
                    "ok": ok,
                    "result": result,
                    "patch": [p.model_dump() for p in patch or []],
                },
                origin,
            )
        return self

    def build(self, **kw: Any) -> Trajectory:
        return Trajectory(episode_id="ep", scenario=scenario(), events=self.events, **kw)


__all__ = ["T0", "Tb", "chk", "scenario"]
