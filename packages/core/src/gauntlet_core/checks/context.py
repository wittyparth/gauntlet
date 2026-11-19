"""Evaluation context shared by final and prefix evaluation.

Both modes evaluate one list of events. Final evaluation takes the trajectory's events;
prefix evaluation takes the prefix plus a synthetic event for the proposed action.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from gauntlet_core.schema import (
    Event,
    Json,
    Model,
    PatchOp,
    PlantedCanary,
    StateDiff,
    ToolCallView,
    Trajectory,
    WorldSnapshot,
    tool_call_views,
)
from gauntlet_core.schema.journal import RecordChange
from gauntlet_core.world.state import PatchConflict, WorldState

from .matchers import UNRESOLVED, resolve_path

PROPOSED_CALL_ID = "__proposed__"
_ARGS_TEMPLATE = re.compile(r"\{args\.([^}]+)\}")


class ProposedAction(Model):
    """What the agent is about to do: call a tool or deliver a message."""

    kind: Literal["tool_call", "agent_message"]
    tool: str | None = None
    args: Json = {}
    text: str | None = None
    patch: list[PatchOp] = []  # the call's simulated world patch, when the world is ours


class PrefixView(Model):
    """The trajectory so far, as the gateway knows it. `world` is the current folded world
    (None in production, where the world is not ours); `initial_world` lets refs to the
    world at an earlier call be answered."""

    events: list[Event]
    initial_world: WorldSnapshot | None = None
    world: WorldSnapshot | None = None
    canaries: list[PlantedCanary] = []
    tool_risk: dict[str, str] = {}
    honeytools: list[str] = []


@dataclass
class Ctx:
    events: list[Event]
    canaries: list[PlantedCanary] = field(default_factory=list)
    tool_risk: dict[str, str] = field(default_factory=dict)
    honeytools: list[str] = field(default_factory=list)
    initial_world: WorldSnapshot | None = None
    world: WorldSnapshot | None = None  # world after the last event
    base_world: WorldSnapshot | None = None  # prefix mode without initial_world
    base_last_seq: int = 0
    diff: StateDiff | None = None
    scenario: Any = None
    episode_id: str = "prefix"
    prefix: bool = False
    proposed_seq: int | None = None
    judgments: Mapping[str, bool] = field(default_factory=dict)
    _timeline: list[tuple[int, WorldSnapshot]] | None = None
    _views: list[ToolCallView] | None = None

    # -- events ---------------------------------------------------------------------------

    def views(self) -> list[ToolCallView]:
        if self._views is None:
            self._views = tool_call_views(self.events)
        return self._views

    def agent_messages(self) -> list[Event]:
        return [e for e in self.events if e.kind == "agent_message"]

    def last_seq(self) -> int:
        return self.events[-1].seq if self.events else 0

    def upto(self, seq: int) -> Ctx:
        """The same context restricted to events with seq <= `seq`."""
        events = [e for e in self.events if e.seq <= seq]
        diff = self.diff
        if diff is not None:
            keep: list[RecordChange] = [c for c in diff.changes if not c.seqs or min(c.seqs) <= seq]
            diff = StateDiff(changes=keep)
        return dataclasses.replace(
            self,
            events=events,
            world=self.world_before(seq + 1),
            diff=diff,
            _views=None,
            _timeline=self.timeline(),
        )

    # -- worlds ---------------------------------------------------------------------------

    def timeline(self) -> list[tuple[int, WorldSnapshot]]:
        """World snapshots after each patch-carrying tool_result, from `initial_world`."""
        if self._timeline is not None:
            return self._timeline
        out: list[tuple[int, WorldSnapshot]] = []
        if self.initial_world is not None:
            state = WorldState.from_snapshot(self.initial_world)
            for e in self.events:
                if e.kind == "tool_result" and e.payload.get("patch"):
                    try:
                        state.apply([PatchOp.model_validate(p) for p in e.payload["patch"]])
                    except PatchConflict:
                        continue
                    out.append((e.seq, state.snapshot()))
        self._timeline = out
        return out

    def world_before(self, seq: int) -> WorldSnapshot | None:
        """The world as of just before event `seq` (None when unknown)."""
        if self.initial_world is not None:
            snap = self.initial_world
            for s, w in self.timeline():
                if s >= seq:
                    break
                snap = w
            return snap
        if self.base_world is not None and seq > self.base_last_seq:
            return self.base_world
        return None

    # -- trajectory view for detectors ----------------------------------------------------

    def trajectory(self) -> Trajectory:
        return Trajectory.model_construct(
            episode_id=self.episode_id,
            scenario=self.scenario,
            events=self.events,
            initial_world=self.initial_world or {},
            final_world=self.world or {},
            diff=self.diff or StateDiff(),
            canaries=self.canaries,
            tool_risk=self.tool_risk,
            honeytools=self.honeytools,
        )


def ctx_from_trajectory(traj: Trajectory, judgments: Mapping[str, bool] | None = None) -> Ctx:
    return Ctx(
        events=list(traj.events),
        canaries=list(traj.canaries),
        tool_risk=dict(traj.tool_risk),
        honeytools=list(traj.honeytools),
        initial_world=traj.initial_world,
        world=traj.final_world,
        diff=traj.diff,
        scenario=traj.scenario,
        episode_id=traj.episode_id,
        judgments=judgments or {},
    )


def ctx_from_prefix(view: PrefixView, proposed: ProposedAction | None) -> Ctx:
    events = list(view.events)
    last = events[-1] if events else None
    last_seq = last.seq if last else 0
    ctx = Ctx(
        events=events,
        canaries=list(view.canaries),
        tool_risk=dict(view.tool_risk),
        honeytools=list(view.honeytools),
        initial_world=view.initial_world,
        base_world=view.world,
        base_last_seq=last_seq,
        prefix=True,
    )
    when = last.sim_time if last else datetime(1970, 1, 1, tzinfo=UTC)
    seq = last_seq + 1
    world = view.world if view.world is not None else ctx.world_before(seq + 10**9)
    if proposed is not None:
        ctx.proposed_seq = seq
        if proposed.kind == "tool_call":
            payload: Json = {
                "call_id": PROPOSED_CALL_ID,
                "tool": proposed.tool or "",
                "args": proposed.args,
                "via": "wired",
            }
            events.append(
                Event(seq=seq, kind="tool_call", actor="agent", sim_time=when, payload=payload)
            )
            if proposed.patch:
                res: Json = {"call_id": PROPOSED_CALL_ID, "ok": True, "result": None}
                res["patch"] = [p.model_dump() for p in proposed.patch]
                events.append(
                    Event(seq=seq + 1, kind="tool_result", actor="tool", sim_time=when, payload=res)
                )
                world = _patched(world, proposed.patch)
        else:
            payload = {"text": proposed.text or ""}
            events.append(
                Event(seq=seq, kind="agent_message", actor="agent", sim_time=when, payload=payload)
            )
    ctx.world = world
    ctx._timeline = None  # rebuilt over the events including the proposed action
    return ctx


def _patched(world: WorldSnapshot | None, patch: list[PatchOp]) -> WorldSnapshot | None:
    if world is None:
        return None
    state = WorldState.from_snapshot(world)
    try:
        state.apply(patch)
    except PatchConflict:
        return None
    return state.snapshot()


def resolve_ref(ref: str, ctx: Ctx, call: ToolCallView | None) -> Any:
    """Resolve a matcher `ref`. Returns UNRESOLVED when the data is not available.

    `args:<path>` reads the current call's args, `result:<tool>.<path>` the latest earlier
    result of that tool, `world:<collection>/<id-or-{args.x}>/<path>` a world record as of
    the call (or the end of the trajectory outside a call).
    """
    kind, _, rest = ref.partition(":")
    anchor = call.call_seq if call else None
    if kind == "args":
        if call is None:
            return UNRESOLVED
        vals = resolve_path(call.args, rest)
        return vals[0] if vals else UNRESOLVED
    if kind == "result":
        tool, _, path = rest.partition(".")
        for v in reversed(ctx.views()):
            if v.tool != tool or v.result_seq is None or v.ok is False:
                continue
            if anchor is not None and v.call_seq >= anchor:
                continue
            vals = resolve_path(v.result, path)
            return vals[0] if vals else UNRESOLVED
        return UNRESOLVED
    if kind == "world":
        collection, _, tail = rest.partition("/")
        rec_id, _, path = tail.partition("/")
        if call is not None:
            rec_id = _ARGS_TEMPLATE.sub(
                lambda m: str((resolve_path(call.args, m.group(1)) or [""])[0]), rec_id
            )
        world = ctx.world_before(anchor) if anchor is not None else ctx.world
        rec = (world or {}).get(collection, {}).get(rec_id)
        if rec is None:
            return UNRESOLVED
        vals = resolve_path(rec, path)
        return vals[0] if vals else UNRESOLVED
    return UNRESOLVED
