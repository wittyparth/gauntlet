"""Journal, effects, trajectory and run manifest (contracts section 2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from .authoring import AgentVersion, Scenario
from .common import Cost, Json, Model

EventKind = Literal[
    "episode_started",
    "user_message",
    "agent_message",
    "tool_call",
    "tool_result",
    "fault_injected",
    "sim_note",
    "check_result",
    "verdict",
    "episode_ended",
]
Actor = Literal["user", "agent", "tool", "platform"]
Outcome = Literal[
    "passed",
    "failed",
    "invalid_scenario",
    "simulator_error",
    "target_error",
    "platform_error",
    "budget_exhausted",
]
Termination = Literal[
    "user_done",
    "max_turns",
    "agent_stuck",
    "target_unreachable",
    "budget",
    "simulator_drift",
    "error",
]
SCORED_OUTCOMES: frozenset[str] = frozenset({"passed", "failed"})


class Origin(Model):
    trust: Literal["system", "user", "untrusted_external"]
    source: str | None = None
    markers: list[str] = []


class PatchOp(Model):
    op: Literal["add", "replace", "remove"]
    collection: str
    id: str
    value: Json | None = None
    before: Json | None = None


class EventDraft(Model):
    """An event before the store assigns `seq`."""

    kind: EventKind
    actor: Actor
    sim_time: datetime
    wall_ms: int = 0
    payload: Json = {}
    origin: Origin | None = None
    cost: Cost | None = None
    effect_key: str | None = None


class Event(EventDraft):
    seq: int


EffectKind = Literal["llm", "target", "tool", "rng", "human"]  # human: arena input (CQ-P4)


class EffectRecord(Model):
    key: str
    kind: EffectKind
    request_hash: str
    status: Literal["pending", "done", "failed"]
    result: Json | None = None
    cost: Cost | None = None
    # Nested work done while this effect was in flight (hard-cores 1.7a):
    # {"events": <events appended between pending and done>, "ordinals": {kind: <effects started>},
    #  "start": {kind: <ordinal of the first one>}}
    span: Json | None = None


WorldSnapshot = dict[str, dict[str, Json]]


class FieldChange(Model):
    path: str
    old: Any = None
    new: Any = None


class RecordChange(Model):
    collection: str
    id: str
    kind: Literal["added", "removed", "changed"]
    fields: list[FieldChange] = []  # for "changed"
    record: Json | None = None  # new record for added, old record for removed
    seqs: list[int] = []  # tool_result events that caused it


class StateDiff(Model):
    changes: list[RecordChange] = []

    def for_collection(self, collection: str) -> list[RecordChange]:
        return [c for c in self.changes if c.collection == collection]


class PlantedCanary(Model):
    id: str
    kind: str
    value: str
    variants: list[str]


class ToolCallView(Model):
    call_seq: int
    result_seq: int | None
    call_id: str
    tool: str
    args: Json
    ok: bool | None
    result: Any
    error: str | None
    via: str


class Trajectory(Model):
    """Read model handed to checks and evaluators."""

    episode_id: str
    scenario: Scenario
    events: list[Event]
    initial_world: WorldSnapshot = {}
    final_world: WorldSnapshot = {}
    diff: StateDiff = StateDiff()
    canaries: list[PlantedCanary] = []
    tool_risk: dict[str, str] = {}  # tool name -> risk class
    honeytools: list[str] = []

    def messages(self) -> list[Event]:
        return [e for e in self.events if e.kind in ("user_message", "agent_message")]

    def agent_messages(self) -> list[Event]:
        return [e for e in self.events if e.kind == "agent_message"]

    def tool_calls(self) -> list[ToolCallView]:
        return tool_call_views(self.events)


def tool_call_views(events: list[Event]) -> list[ToolCallView]:
    results = {e.payload["call_id"]: e for e in events if e.kind == "tool_result"}
    out: list[ToolCallView] = []
    for e in events:
        if e.kind != "tool_call":
            continue
        r = results.get(e.payload["call_id"])
        out.append(
            ToolCallView(
                call_seq=e.seq,
                result_seq=r.seq if r else None,
                call_id=e.payload["call_id"],
                tool=e.payload["tool"],
                args=e.payload.get("args", {}),
                ok=r.payload.get("ok") if r else None,
                result=r.payload.get("result") if r else None,
                error=r.payload.get("error") if r else None,
                via=e.payload.get("via", "hosted"),
            )
        )
    return out


class RunManifest(Model):
    run_id: str
    suite_id: str
    agent_version: AgentVersion
    scenario_versions: dict[str, int]
    seed: int
    repetitions: int
    model_roles: dict[str, str]
    rubric_versions: dict[str, int] = {}
    platform_version: str
    budget_usd_micros: int
    created_at: datetime
