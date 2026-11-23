"""`gauntlet demo seed`: ask a dev-mode server to load the demo data."""

from __future__ import annotations

import json
import os
from typing import Annotated

import httpx
import typer

demo_app = typer.Typer(help="Demo data helpers.", no_args_is_help=True)


@demo_app.command("seed")
def seed(
    api_url: Annotated[str, typer.Option("--api-url")] = "http://localhost:8000",
    api_key: Annotated[str | None, typer.Option("--api-key", envvar="GAUNTLET_API_KEY")] = None,
    reset: Annotated[
        bool, typer.Option("--reset", help="Delete existing demo data first.")
    ] = False,
) -> None:
    """POST /v1/dev/seed and print the created ids."""
    headers = {"Authorization": f"Bearer {api_key or os.environ.get('GAUNTLET_API_KEY', '')}"}
    url = api_url.rstrip("/") + "/v1/dev/seed"
    try:
        resp = httpx.post(url, headers=headers, json={"reset": reset}, timeout=30)
    except httpx.HTTPError as e:
        typer.echo(f"cannot reach {api_url}: {e}", err=True)
        raise typer.Exit(3) from e
    if resp.status_code in (404, 403):
        typer.echo(
            "the server refused the seed request: it is not running in dev mode. "
            "On a prod deployment run `docker compose exec api python -m gauntlet_server.demo "
            "seed` instead (no model calls); see deploy/README.md",
            err=True,
        )
        raise typer.Exit(3)
    if resp.status_code >= 400:
        typer.echo(f"seed failed: HTTP {resp.status_code}: {resp.text[:200]}", err=True)
        raise typer.Exit(3)
    typer.echo(json.dumps(resp.json(), indent=2))
