"""`python -m gauntlet_server.demo seed`: prod-safe demo data, no model calls.

Loads the ecommerce pack, the support agent, its suites, two finished scripted runs (one with a
failing episode, one to compare against) and a published policy with proposals. The runs execute
through the real runner with a scripted model, so nothing touches the network or a provider key.
Idempotent; `--reset` rebuilds the demo rows. The DVA agents need no rows: point a campaign at
http://dva:8100 (see docs/demo/DEMO_SCRIPT.md)."""

from __future__ import annotations

import argparse
import asyncio
import json

from sqlalchemy.ext.asyncio import AsyncSession

from .app import build_state
from .auth import ensure_default_workspace
from .config import Settings
from .db import models as m
from .services.seed import PROJECT, WORLD, pack, seed_demo

__all__ = ["main", "seed"]


DVA_AGENT, DVA_VERSION = "agt_dva", "agv_dva_wired"


async def _seed_dva(s: AsyncSession, ws: str) -> None:
    """The wired Damn Vulnerable Agent as a target (compose service `dva`, internal network)."""
    if await s.get(m.Agent, DVA_AGENT) is None:
        s.add(
            m.Agent(
                id=DVA_AGENT,
                workspace_id=ws,
                project_id=PROJECT,
                name="Damn Vulnerable Agent (wired)",
            )
        )
        await s.flush()
    if await s.get(m.AgentVersion, DVA_VERSION) is None:
        s.add(
            m.AgentVersion(
                id=DVA_VERSION,
                workspace_id=ws,
                agent_id=DVA_AGENT,
                label="dva-wired",
                world_id=WORLD,
                config={
                    "target": {
                        "kind": "openai_compat",
                        "base_url": "http://dva:8100/v1",
                        "model": "dva",
                        "wired": True,
                    },
                    "profile": {
                        "purpose": "Customer support for an online outdoor gear store",
                        "policies_text": pack().policy_text,
                    },
                },
            )
        )


async def seed(settings: Settings, *, reset: bool = False) -> dict[str, object]:
    state = await build_state(settings)
    try:
        async with state.sm() as s, s.begin():
            ws = await ensure_default_workspace(s)
        out = await seed_demo(state, ws, reset=reset, compare_run=True, gateway=True)
        async with state.sm() as s, s.begin():
            await _seed_dva(s, ws)
        return {**out, "dva_agent_id": DVA_AGENT, "dva_agent_version_id": DVA_VERSION}
    finally:
        for close in state.closers:
            await close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="gauntlet_server.demo")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("seed", help="create the demo workspace data (no model calls)")
    sp.add_argument("--reset", action="store_true", help="delete the demo rows first")
    args = parser.parse_args()
    out = asyncio.run(seed(Settings.from_env(), reset=args.reset))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
