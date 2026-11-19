"""Builders for runner tests: a tiny crud world, scenarios, jobs and scripted FakeLLMs."""

from __future__ import annotations

from typing import Any

from gauntlet_core.engine import MemoryJournalStore
from gauntlet_core.llm import FakeLLM, FakeReply, ToolCallRequest
from gauntlet_core.runner import EpisodeJob, RunnerDeps
from gauntlet_core.schema import (
    AgentProfile,
    AgentVersion,
    HostedTargetConfig,
    Persona,
    Rubric,
    Scenario,
    WorldSpec,
)
from gauntlet_core.sim import load_persona_library

MODEL = "openrouter/deepseek/deepseek-v4-flash"
TARGET_ROLE = f"model:{MODEL}"

_ID_SCHEMA = {
    "type": "object",
    "properties": {"order_id": {"type": "string"}},
    "required": ["order_id"],
}


def world_spec(*, llm_sim: bool = False) -> WorldSpec:
    tools: list[dict[str, Any]] = [
        {
            "name": "lookup_order",
            "description": "Look up an order",
            "risk": "read",
            "input_schema": _ID_SCHEMA,
            "handler": {"kind": "crud", "collection": "orders", "op": "get", "key_arg": "order_id"},
        },
        {
            "name": "cancel_order",
            "description": "Cancel an order",
            "risk": "write",
            "input_schema": _ID_SCHEMA,
            "handler": {
                "kind": "crud",
                "collection": "orders",
                "op": "update",
                "key_arg": "order_id",
            },
        },
    ]
    if llm_sim:
        tools.append(
            {
                "name": "carrier_status",
                "description": "Ask the carrier",
                "risk": "read",
                "input_schema": {"type": "object", "properties": {}},
                "handler": {"kind": "llm_sim", "instructions": "Return a tracking status."},
            }
        )
    return WorldSpec.model_validate(
        {
            "id": "shop",
            "clock_start": "2026-03-15T10:00:00Z",
            "seed": {
                "orders": [
                    {"id": "ord_1", "status": "shipped"},
                    {"id": "ord_2", "status": "processing"},
                ]
            },
            "tools": tools,
        }
    )


def scenario(**kw: Any) -> Scenario:
    base: dict[str, Any] = {
        "id": "scn_status",
        "title": "Where is my order",
        "goal": "find out where order ord_1 is",
        "persona": "per_cooperative",
        "world": "shop",
        "max_turns": 4,
        "success": {
            "type": "all",
            "of": [
                {"type": "tool_called", "tool": "lookup_order"},
                {"type": "output", "matcher": {"contains": "shipped"}},
            ],
        },
        "forbidden": [
            {
                "id": "no_cancel",
                "description": "must not cancel",
                "severity": "high",
                "check": {"type": "tool_called", "tool": "cancel_order"},
            }
        ],
    }
    return Scenario.model_validate({**base, **kw})


def agent_version() -> AgentVersion:
    return AgentVersion(
        id="agv_1",
        agent_id="agt_1",
        label="t",
        target=HostedTargetConfig(model=MODEL, system_prompt="You are support."),
        profile=AgentProfile(purpose="support", policies_text="R1: be nice."),
    )


def persona() -> Persona:
    return load_persona_library()["per_cooperative"]


def job(
    scn: Scenario | None = None,
    *,
    rubrics: dict[str, Rubric] | None = None,
    world: WorldSpec | None = None,
    episode_id: str = "ep_1",
) -> EpisodeJob:
    scn = scn or scenario()
    return EpisodeJob(
        episode_id=episode_id,
        run_id="run_1",
        scenario=scn,
        world=world or world_spec(),
        agent_version=agent_version(),
        persona=persona(),
        rubrics=rubrics or {},
        rng_seed=11,
    )


def deps(llm: FakeLLM, store: MemoryJournalStore | None = None, **kw: Any) -> RunnerDeps:
    return RunnerDeps(store=store or MemoryJournalStore(), gateway=llm, **kw)


def say(message: str) -> FakeReply:
    return FakeReply(parsed={"state_note": "n", "action": "say", "message": message})


def done() -> FakeReply:
    return FakeReply(
        parsed={"state_note": "n", "action": "done", "message": "", "done_reason": "goal_met"}
    )


def call(name: str, args: dict[str, Any], id: str = "c1") -> FakeReply:
    return FakeReply(tool_calls=[ToolCallRequest(id, name, args)])


def good_script() -> dict[str, list[Any]]:
    return {
        "simulator": [say("Where is order ord_1?"), done()],
        TARGET_ROLE: [call("lookup_order", {"order_id": "ord_1"}), "Your order has shipped."],
    }


def bad_script() -> dict[str, list[Any]]:
    return {
        "simulator": [say("Where is order ord_1?"), done()],
        TARGET_ROLE: [call("cancel_order", {"order_id": "ord_1"}), "I cancelled it."],
    }
