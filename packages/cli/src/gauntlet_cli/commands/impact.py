"""`gauntlet impact`: which scenarios to re-run after a change between two agent versions
(P5-7). Read-only; the exit code is 0 whatever the selection (it is advice, not a gate)."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from .remote import Api, ApiFailure

__all__ = ["impact"]


def impact(
    from_version: Annotated[str, typer.Option("--from", help="Agent version id before.")],
    to_version: Annotated[str, typer.Option("--to", help="Agent version id after.")],
    policy_from: Annotated[
        str | None, typer.Option(help="Policy id (or id@version) before.")
    ] = None,
    policy_to: Annotated[str | None, typer.Option(help="Policy id (or id@version) after.")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output.")] = False,
    api_url: Annotated[
        str, typer.Option("--api-url", envvar="GAUNTLET_API_URL", help="Gauntlet server url.")
    ] = "http://localhost:8000",
    api_key: Annotated[
        str | None, typer.Option("--api-key", envvar="GAUNTLET_API_KEY", help="API key.")
    ] = None,
) -> None:
    """Select the scenarios a change can affect, with a reason for each."""
    body = {"from_version": from_version, "to_version": to_version}
    if policy_from or policy_to:
        body |= {"policy_from": policy_from, "policy_to": policy_to}
    try:
        out = Api(api_url, api_key).post("/v1/impact", body)
    except ApiFailure as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(3) from e
    if as_json:
        typer.echo(json.dumps(out, indent=2, sort_keys=True))
        return
    ch = out["change"]
    kinds = (
        [k for k in ("model", "prompt") if ch[k]]
        + (["tools"] if ch["tools"] else [])
        + (["policy"] if ch["policy_clauses"] else [])
        + (["world"] if ch["worlds"] else [])
        + (["unknown"] if ch["unknown"] else [])
    )
    typer.echo(f"change: {', '.join(kinds) or 'none'}")
    mode = (
        "full run" if out["full_run"] else f"{len(out['scenario_ids'])} of {out['total_scenarios']}"
    )
    typer.echo(f"selected: {mode}")
    for sid in out["scenario_ids"]:
        typer.echo(f"  {sid}: {'; '.join(out['reasons'][sid])}")
