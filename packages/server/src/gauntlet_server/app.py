"""FastAPI app. Stub until P1-9 adds the REST API; keep `gauntlet_server.app:app`."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from fastapi import FastAPI

__all__ = ["app"]


def _version() -> str:
    try:
        return version("gauntlet-server")
    except PackageNotFoundError:
        return "0.0.0"


app = FastAPI(title="Gauntlet", version=_version())


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "version": _version()}
