"""`gauntlet cassette export|import`: move cassettes to and from a Gauntlet server."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated

import httpx
import typer

cassette_app = typer.Typer(help="Export and import cassettes (the journal of an episode).")

ApiUrl = Annotated[
    str, typer.Option("--api-url", envvar="GAUNTLET_API_URL", help="Gauntlet server url.")
]
ApiKey = Annotated[
    str | None, typer.Option("--api-key", envvar="GAUNTLET_API_KEY", help="API key.")
]


def _headers(api_key: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key or os.environ.get('GAUNTLET_API_KEY', '')}"}


def _fail(resp: httpx.Response) -> typer.Exit:
    try:
        err = resp.json()["error"]
        detail = f"{err['code']}: {err['message']}"
        if err.get("detail"):
            detail += f" {json.dumps(err['detail'])}"
    except (ValueError, KeyError, TypeError):
        detail = resp.text[:200]
    typer.echo(f"server answered {resp.status_code}: {detail}", err=True)
    return typer.Exit(1)


@cassette_app.command("export")
def export(
    episode_id: Annotated[str, typer.Argument(help="Episode id.")],
    out: Annotated[Path, typer.Option("-o", "--out", help="File to write.")],
    api_url: ApiUrl = "http://localhost:8000",
    api_key: ApiKey = None,
) -> None:
    """Download EPISODE_ID's cassette (secrets redacted by the server)."""
    url = api_url.rstrip("/") + f"/v1/episodes/{episode_id}/cassette"
    try:
        resp = httpx.get(url, headers=_headers(api_key), timeout=60)
    except httpx.HTTPError as e:
        typer.echo(f"cannot reach {api_url}: {e}", err=True)
        raise typer.Exit(1) from e
    if resp.status_code != 200:
        raise _fail(resp)
    out.write_text(resp.text)
    typer.echo(f"wrote {out} ({len(resp.text.splitlines())} lines)")


@cassette_app.command("import")
def import_(
    file: Annotated[Path, typer.Argument(help="Cassette file (NDJSON).")],
    agent_version_id: Annotated[
        str | None, typer.Option("--agent-version", help="Attribute it to this agent version.")
    ] = None,
    api_url: ApiUrl = "http://localhost:8000",
    api_key: ApiKey = None,
) -> None:
    """Upload FILE as an imported episode (a `purpose=import` run, hidden from run lists)."""
    if not file.is_file():
        typer.echo(f"{file}: no such file", err=True)
        raise typer.Exit(2)
    params = {"agent_version_id": agent_version_id} if agent_version_id else {}
    url = api_url.rstrip("/") + "/v1/cassettes"
    try:
        resp = httpx.post(
            url,
            params=params,
            content=file.read_bytes(),
            headers={**_headers(api_key), "Content-Type": "application/x-ndjson"},
            timeout=120,
        )
    except httpx.HTTPError as e:
        typer.echo(f"cannot reach {api_url}: {e}", err=True)
        raise typer.Exit(1) from e
    if resp.status_code != 201:
        raise _fail(resp)
    body = resp.json()
    typer.echo(f"imported as episode {body['episode_id']} in run {body['run_id']}")
