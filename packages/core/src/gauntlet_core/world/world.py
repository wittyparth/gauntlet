"""Building a world from a spec, executing tools inside an episode, and turning a journal
back into a Trajectory."""

from __future__ import annotations

import copy
import json
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from gauntlet_core.engine.ctx import EpisodeCtx
from gauntlet_core.schema import (
    DocumentSpec,
    Event,
    EventDraft,
    Json,
    Origin,
    PatchOp,
    PlantedCanary,
    Scenario,
    ToolSpec,
    Trajectory,
    WorldSnapshot,
    WorldSpec,
)

from .canary import plant
from .state import WorldState, WorldView, diff_from_patches
from .tools import (
    NeedsLLM,
    ToolOutcome,
    apply_fault,
    pick_fault,
    resolve_handler,
    validate_args,
)

LLMSim = Callable[[EpisodeCtx, ToolSpec, Json], Awaitable[Any]]


@dataclass
class BuiltWorld:
    spec: WorldSpec
    initial: WorldSnapshot
    tools: dict[str, ToolSpec]
    canaries: list[PlantedCanary]
    system_context: list[str] = field(default_factory=list)  # canaries for the system prompt
    documents: dict[str, DocumentSpec] = field(default_factory=dict)
    tool_result_canaries: dict[str, list[str]] = field(default_factory=dict)  # tool -> values
    markers: list[str] = field(default_factory=list)  # taint markers planted by injections


def _merge_seed(seed: dict[str, list[Json]], overrides: Json) -> dict[str, list[Json]]:
    out = {c: [copy.deepcopy(r) for r in recs] for c, recs in seed.items()}
    for collection, recs in (overrides or {}).items():
        by_id = {str(r["id"]): r for r in out.setdefault(collection, [])}
        for rec in recs:
            rid = str(rec["id"])
            if rid in by_id:
                by_id[rid].update(copy.deepcopy(rec))
            else:
                out[collection].append(copy.deepcopy(rec))
    return out


def build_world(spec: WorldSpec, overrides: Json | None, episode_seed: int) -> BuiltWorld:
    seed = _merge_seed(spec.seed, overrides or {})
    docs = {d.id: d for d in spec.documents}
    built = BuiltWorld(
        spec=spec, initial={}, tools={t.name: t for t in spec.tools}, canaries=[], documents=docs
    )
    for c in spec.canaries:
        planted = plant(c, episode_seed)
        built.canaries.append(planted)
        if c.placement == "system_prompt":
            built.system_context.append(f"{c.location}: {planted.value}")
        elif c.placement == "world_record":
            collection, rid, fld = c.location.split("/", 2)
            rec = next((r for r in seed.get(collection, []) if str(r["id"]) == rid), None)
            if rec is None:
                raise ValueError(f"canary {c.id}: no record {collection}/{rid}")
            rec[fld] = planted.value
        elif c.placement == "document":
            d = docs[c.location]
            docs[c.location] = d.model_copy(update={"body": f"{d.body}\n{planted.value}"})
        else:
            built.tool_result_canaries.setdefault(c.location, []).append(planted.value)
    built.initial = WorldState.from_seed(seed).snapshot()
    return built


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    ok: bool
    result: Any
    error: str | None

    def as_text(self) -> str:
        """What the agent sees."""
        body = {"error": self.error} if not self.ok else self.result
        return body if isinstance(body, str) else json.dumps(body, default=str)


class World:
    """The mock world inside one episode execution. State lives in memory and is rebuilt
    on resume because every tool call is a recorded effect whose result carries its patch."""

    def __init__(self, built: BuiltWorld, llm_sim: LLMSim | None = None) -> None:
        self.built = built
        self.state = WorldState.from_snapshot(built.initial)
        self._initial = WorldState.from_snapshot(built.initial)
        self._calls: Counter[str] = Counter()
        self._n = 0
        self._llm_sim = llm_sim

    def bind(self, ctx: EpisodeCtx) -> None:
        """Register as the ctx's replay hook (1.7a): tool results that were produced inside a
        nested span, or by another process, are folded into this world's state."""
        ctx.state["world"] = self
        ctx.add_replay_hook(self.apply_events)

    def apply_events(self, events: Sequence[Event]) -> None:
        """Fold journal events this execution did not produce itself."""
        for e in events:
            if e.kind == "tool_call":
                self._n += 1
                self._calls[e.payload["tool"]] += 1
            elif e.kind == "tool_result" and e.payload.get("patch"):
                self.state.apply([PatchOp.model_validate(p) for p in e.payload["patch"]])

    def snapshot(self) -> WorldSnapshot:
        return self.state.snapshot()

    def tool_schemas(self, subset: list[str] | None = None) -> list[Json]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            }
            for t in self.built.tools.values()
            if subset is None or t.name in subset
        ]

    def _execute(self, spec: ToolSpec, args: Json, ctx: EpisodeCtx, index: int, roll: float):
        """Pure given (state, args, sim time, roll). Returns the effect result dict."""
        err = validate_args(spec.input_schema, args)
        if err:
            return {"ok": False, "result": None, "error": f"invalid_args: {err}", "patch": []}
        handler = resolve_handler(spec)
        now = ctx.now()
        fault = pick_fault(self.built.spec.faults, spec.name, index, roll)
        latency = 0
        if fault is None:
            out = handler(WorldView(self.state), args, now)
        else:
            out, latency = apply_fault(
                fault,
                lambda: handler(WorldView(self.state), args, now),
                lambda: handler(WorldView(self._initial), args, now),
            )
        self.state.check(out.patch)
        result = out.result
        extra = self.built.tool_result_canaries.get(spec.name)
        if extra and out.error is None and isinstance(result, dict):
            result = {**result, "internal_note": " ".join(extra)}
        return {
            "ok": out.error is None,
            "result": result,
            "error": out.error,
            "patch": [p.model_dump(mode="json") for p in out.patch],
            "fault": fault.model_dump(mode="json") if fault else None,
            "latency_ms": latency,
        }

    async def call_tool(
        self, ctx: EpisodeCtx, tool: str, args: Json, *, via: str = "hosted"
    ) -> ToolResult:
        ctx.add_replay_hook(self.apply_events)  # no-op when already bound
        call_id = f"call_{self._n}"
        call_n = self._n
        self._n += 1
        await ctx.emit(
            EventDraft(
                kind="tool_call",
                actor="agent",
                sim_time=ctx.now(),
                payload={"call_id": call_id, "tool": tool, "args": args, "via": via},
            )
        )
        spec = self.built.tools.get(tool)
        index = self._calls[tool]
        self._calls[tool] += 1
        roll = ctx.random(call_n)

        async def run() -> tuple[Json, None]:
            if spec is None:
                return {"ok": False, "result": None, "error": "unknown_tool", "patch": []}, None
            try:
                return self._execute(spec, args, ctx, index, roll), None
            except NeedsLLM:
                if self._llm_sim is None:
                    return {
                        "ok": False,
                        "result": None,
                        "error": "llm_sim_unavailable",
                        "patch": [],
                    }, None
                result = await self._llm_sim(ctx, spec, args)
                return {"ok": True, "result": result, "error": None, "patch": []}, None

        res = await ctx.effect(
            "tool", {"tool": tool, "args": args, "index": index}, run, retry_safe=True
        )
        # applied on both the live and the replay path: this is what rebuilds state on resume
        patch = [PatchOp.model_validate(p) for p in res.get("patch", [])]
        self.state.apply(patch)

        if res.get("fault"):
            await ctx.emit(
                EventDraft(
                    kind="fault_injected",
                    actor="platform",
                    sim_time=ctx.now(),
                    payload={"call_id": call_id, "fault": res["fault"]},
                )
            )
        untrusted = bool(spec and spec.untrusted_output)
        text = json.dumps(res.get("result"), default=str)
        origin = Origin(
            trust="untrusted_external" if untrusted else "system",
            source=tool,
            markers=[m for m in self.built.markers if m in text] if untrusted else [],
        )
        await ctx.emit(
            EventDraft(
                kind="tool_result",
                actor="tool",
                sim_time=ctx.now(),
                wall_ms=ctx.last_effect_ms + int(res.get("latency_ms") or 0),
                payload={
                    "call_id": call_id,
                    "ok": res["ok"],
                    "result": res.get("result"),
                    "patch": res.get("patch", []),
                    "error": res.get("error"),
                },
                origin=origin,
            )
        )
        return ToolResult(call_id, res["ok"], res.get("result"), res.get("error"))


def fold_world(initial: WorldSnapshot, events: list[Event]) -> tuple[WorldSnapshot, Any]:
    """Final snapshot and StateDiff implied by the tool_result events of a journal."""
    state = WorldState.from_snapshot(initial)
    patches: list[tuple[int, list[PatchOp]]] = []
    for e in events:
        if e.kind == "tool_result" and e.payload.get("patch"):
            patch = [PatchOp.model_validate(p) for p in e.payload["patch"]]
            state.apply(patch)
            patches.append((e.seq, patch))
    return state.snapshot(), diff_from_patches(initial, patches)


def build_trajectory(
    episode_id: str, scenario: Scenario, events: list[Event], built: BuiltWorld
) -> Trajectory:
    final, diff = fold_world(built.initial, events)
    return Trajectory(
        episode_id=episode_id,
        scenario=scenario,
        events=events,
        initial_world=built.initial,
        final_world=final,
        diff=diff,
        canaries=built.canaries,
        tool_risk={t.name: t.risk for t in built.tools.values()},
        honeytools=[t.name for t in built.tools.values() if t.honeytool],
    )


__all__ = [
    "BuiltWorld",
    "ToolOutcome",
    "ToolResult",
    "World",
    "build_trajectory",
    "build_world",
    "fold_world",
]
