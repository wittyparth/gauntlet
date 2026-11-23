"""`python -m gauntlet_server.bootstrap`: create ws_default, a project and an admin key.

Idempotent: with a workspace present it only upserts the dev key (when GAUNTLET_ENV=dev) unless
`--new-key` is given, which mints and prints a fresh admin key once."""

from __future__ import annotations

import argparse
import asyncio
import os

from .auth import DEFAULT_WORKSPACE, ensure_default_workspace, generate_key, upsert_key
from .config import Settings
from .db import make_engine, make_sessionmaker
from .db.models import Workspace

__all__ = ["bootstrap", "main"]


async def bootstrap(settings: Settings, *, new_key: bool = False) -> str | None:
    engine = make_engine(settings.database_url)
    sm = make_sessionmaker(engine)
    printed: str | None = None
    try:
        async with sm() as s, s.begin():
            fresh = await s.get(Workspace, DEFAULT_WORKSPACE) is None
            ws = await ensure_default_workspace(s)
            if settings.is_dev and settings.dev_api_key:
                await upsert_key(s, ws, settings.dev_api_key, "dev")
            admin_key = os.environ.get("GAUNTLET_ADMIN_API_KEY", "")
            if admin_key:  # deploy-generated admin key (see deploy/bootstrap.sh); idempotent
                if not admin_key.startswith("gk_") or len(admin_key) < 24:
                    raise SystemExit("GAUNTLET_ADMIN_API_KEY must look like gk_ + 20 or more chars")
                await upsert_key(s, ws, admin_key, "admin")
            elif fresh or new_key:
                printed = generate_key()
                await upsert_key(s, ws, printed, "admin")
    finally:
        await engine.dispose()
    return printed


def main() -> None:
    parser = argparse.ArgumentParser(prog="gauntlet_server.bootstrap")
    parser.add_argument("--new-key", action="store_true")
    args = parser.parse_args()
    key = asyncio.run(bootstrap(Settings.from_env(), new_key=args.new_key))
    if key:
        print(f"admin API key (shown once): {key}")


if __name__ == "__main__":
    main()
