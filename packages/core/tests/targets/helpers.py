"""Shared builders for target tests: a tiny crud world and ctx/scenario helpers."""

from __future__ import annotations

from gauntlet_core.engine import EpisodeCtx, MemoryJournalStore
from gauntlet_core.schema import Scenario, WorldSpec
from gauntlet_core.world import World, build_world

SPEC = WorldSpec.model_validate(
    {
        "id": "w",
        "clock_start": "2026-01-01T09:00:00Z",
        "seed": {
            "orders": [{"id": "ord_1", "status": "shipped"}, {"id": "ord_2", "status": "new"}]
        },
        "tools": [
            {
                "name": "lookup_order",
                "description": "Look up an order",
                "risk": "read",
                "input_schema": {
                    "type": "object",
                    "properties": {"order_id": {"type": "string"}},
                    "required": ["order_id"],
                },
                "handler": {
                    "kind": "crud",
                    "collection": "orders",
                    "op": "get",
                    "key_arg": "order_id",
                },
            },
            {
                "name": "cancel_order",
                "description": "Cancel an order",
                "risk": "write",
                "input_schema": {
                    "type": "object",
                    "properties": {"order_id": {"type": "string"}},
                    "required": ["order_id"],
                },
                "handler": {
                    "kind": "crud",
                    "collection": "orders",
                    "op": "update",
                    "key_arg": "order_id",
                },
            },
        ],
        "canaries": [
            {"id": "k", "kind": "api_key", "placement": "system_prompt", "location": "ops key"}
        ],
    }
)


def scenario(max_turns: int = 6) -> Scenario:
    return Scenario.model_validate(
        {
            "id": "scn",
            "title": "t",
            "goal": "g",
            "persona": "p",
            "world": "w",
            "max_turns": max_turns,
            "success": {"type": "output", "matcher": {"contains": "ship"}},
        }
    )


async def make_ctx(store: MemoryJournalStore | None = None, *, world: bool = True) -> EpisodeCtx:
    store = store or MemoryJournalStore()
    ctx = await EpisodeCtx.open(store, "ep", run_id="r", rng_seed=7)
    if world:
        ctx.state["world"] = World(build_world(SPEC, None, 7))
    return ctx


def new_world() -> World:
    return World(build_world(SPEC, None, 7))
