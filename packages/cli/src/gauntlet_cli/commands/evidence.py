"""`gauntlet evidence create` and `gauntlet evidence verify` (P5-7).

`create` asks the server to build a pack, waits for it and downloads the zip. `verify` works
offline: checksums, the embedded audit-chain excerpt and, with a public key (or the one in the
manifest), the signature. Exit codes: 0 verified, 1 verification failed, 2 usage, 3 platform
error."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Annotated

import typer
from gauntlet_core.evidence import verify_pack

from .remote import Api, ApiFailure

__all__ = ["evidence_app"]

evidence_app = typer.Typer(help="Evidence packs: build and verify.", no_args_is_help=True)

POLL_S = 3.0
_sleep = time.sleep


@evidence_app.command("create")
def create(
    agent_version: Annotated[str, typer.Option("--agent-version", help="Agent version id.")],
    framework: Annotated[
        list[str] | None, typer.Option("--framework", help="owasp-llm, owasp-agentic, nist-ai-rmf")
    ] = None,
    out: Annotated[Path, typer.Option("-o", "--out", help="Where to write the zip.")] = Path(
        "evidence-pack.zip"
    ),
    timeout_s: Annotated[int, typer.Option("--timeout", help="Seconds to wait.")] = 600,
    api_url: Annotated[
        str, typer.Option("--api-url", envvar="GAUNTLET_API_URL", help="Gauntlet server url.")
    ] = "http://localhost:8000",
    api_key: Annotated[
        str | None, typer.Option("--api-key", envvar="GAUNTLET_API_KEY", help="API key.")
    ] = None,
) -> None:
    """Build an evidence pack on the server and download it."""
    api = Api(api_url, api_key)
    try:
        pack = api.post(
            "/v1/evidence-packs",
            {"agent_version_id": agent_version, "frameworks": framework or ["owasp-llm"]},
        )
        waited = 0.0
        while pack["status"] in ("queued", "running"):
            if waited >= timeout_s:
                typer.echo(f"timed out; the pack {pack['id']} keeps building", err=True)
                raise typer.Exit(3)
            _sleep(POLL_S)
            waited += POLL_S
            pack = api.get(f"/v1/evidence-packs/{pack['id']}")
        if pack["status"] != "done":
            typer.echo(f"the pack failed: {pack.get('error')}", err=True)
            raise typer.Exit(3)
        out.write_bytes(api.download(f"/v1/evidence-packs/{pack['id']}/download"))
    except ApiFailure as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(3) from e
    note = "" if pack["signed"] else " (unsigned: no signing key is configured on the server)"
    typer.echo(f"wrote {out} (sha256 {pack['sha256']}){note}")


@evidence_app.command("verify")
def verify(
    pack: Annotated[Path, typer.Argument(help="The evidence pack zip.")],
    public_key: Annotated[
        str | None, typer.Option("--public-key", help="Ed25519 public key, base64.")
    ] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Check checksums, the audit-chain excerpt and the signature, offline."""
    try:
        data = pack.read_bytes()
    except OSError as e:
        typer.echo(f"cannot read {pack}: {e.strerror}", err=True)
        raise typer.Exit(2) from e
    rep = verify_pack(data, public_key_b64_=public_key)
    if as_json:
        typer.echo(json.dumps({
            "ok": rep.ok, "checksums": rep.checksums, "audit_chain": rep.audit_chain,
            "signature": rep.signature, "files": rep.files, "problems": rep.problems,
        }, indent=2))  # fmt: skip
    else:
        typer.echo(f"checksums:   {'ok' if rep.checksums else 'FAILED'} ({rep.files} files)")
        typer.echo(f"audit chain: {rep.audit_chain}")
        typer.echo(f"signature:   {rep.signature}")
        for p in rep.problems:
            typer.echo(f"problem: {p}", err=True)
    raise typer.Exit(0 if rep.ok else 1)
