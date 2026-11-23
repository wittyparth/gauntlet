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

from .app import build_state
from .auth import ensure_default_workspace
from .config import Settings
from .services.seed import seed_demo

__all__ = ["main", "seed"]


async def seed(settings: Settings, *, reset: bool = False) -> dict[str, object]:
    state = await build_state(settings)
    try:
        async with state.sm() as s, s.begin():
            ws = await ensure_default_workspace(s)
        return await seed_demo(state, ws, reset=reset, compare_run=True, gateway=True)
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
