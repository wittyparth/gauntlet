"""`gauntlet run --remote`: start a run on a Gauntlet server and wait for it (P3-4), plus the
small API client the `gate` command shares."""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx
import typer

__all__ = ["Api", "ApiFailure", "resolve_baseline", "run_remote", "web_url_for"]

POLL_S = 5.0
TERMINAL = ("done", "cancelled", "failed")

# Indirection so tests can run the polling loop on a fast clock.
_sleep = time.sleep
_now = time.monotonic


class ApiFailure(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"server answered {status}: {detail}")
        self.status = status


class Api:
    def __init__(self, api_url: str, api_key: str | None, timeout: float = 60.0) -> None:
        self.base = api_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_key or os.environ.get('GAUNTLET_API_KEY', '')}"
        }
        self._timeout = timeout

    def request(self, method: str, path: str, **kw: Any) -> Any:
        try:
            resp = httpx.request(
                method, self.base + path, headers=self._headers, timeout=self._timeout, **kw
            )
        except httpx.HTTPError as e:
            raise ApiFailure(0, f"cannot reach {self.base}: {e}") from e
        if resp.status_code >= 400:
            try:
                err = resp.json()["error"]
                detail = f"{err['code']}: {err['message']}"
            except (ValueError, KeyError, TypeError):
                detail = resp.text[:200]
            raise ApiFailure(resp.status_code, detail)
        return resp.json()

    def get(self, path: str, **params: Any) -> Any:
        return self.request("GET", path, params={k: v for k, v in params.items() if v is not None})

    def post(self, path: str, body: dict[str, Any]) -> Any:
        return self.request("POST", path, json=body)


def web_url_for(api_url: str, web_url: str | None) -> str:
    """`<api-url minus /api>`, unless the web app lives on another host (`--web-url`)."""
    if web_url:
        return web_url.rstrip("/")
    base = api_url.rstrip("/")
    return base[: -len("/api")] if base.endswith("/api") else base


def resolve_baseline(api: Api, suite_id: str, baseline: str | None, label: str) -> str | None:
    """`auto`: the most recent completed run of the suite whose agent version label equals
    `label` (the server has no label filter, so it is applied here)."""
    if baseline != "auto":
        return baseline
    page = api.get("/v1/runs", suite_id=suite_id, status="done", limit=50)
    for run in page["items"]:
        if run["manifest"]["agent_version"]["label"] == label:
            return str(run["id"])
    return None


def _progress(run: dict[str, Any]) -> str:
    c = run["counts"]
    spent = run["spent_usd_micros"] / 1_000_000
    return f"{c['done'] + c['cancelled']}/{c['total']} episodes, spent ${spent:.4f}"


def run_remote(
    *,
    api_url: str,
    api_key: str | None,
    suite: str | None,
    agent_version: str | None,
    reps: int | None,
    budget_usd: float,
    baseline: str | None,
    baseline_label: str,
    wait: bool,
    timeout_min: float,
    web_url: str | None,
    seed: int | None,
    adaptive: bool,
    json_out: bool,
) -> None:
    if not suite or not agent_version:
        typer.echo("--remote needs --suite SUITE_ID and --agent-version VERSION_ID", err=True)
        raise typer.Exit(2)
    api = Api(api_url, api_key)
    try:
        base_id = resolve_baseline(api, suite, baseline, baseline_label)
        body: dict[str, Any] = {
            "suite_id": suite,
            "agent_version_id": agent_version,
            "budget_usd_micros": round(budget_usd * 1_000_000),
            "adaptive": adaptive,
        }
        if reps is not None:
            body["repetitions"] = reps
        if seed is not None:
            body["seed"] = seed
        if base_id:
            body["baseline_run_id"] = base_id
        run = api.post("/v1/runs", body)
    except ApiFailure as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(2 if 400 <= e.status < 500 else 3) from e
    run_id = run["id"]
    url = f"{web_url_for(api_url, web_url)}/runs/{run_id}"
    typer.echo(f"run {run_id} started: {url}", err=True)
    if baseline == "auto":
        typer.echo(f"baseline: {base_id or 'none found'}", err=True)

    status = run["status"]
    if wait:
        deadline = _now() + timeout_min * 60
        last = ""
        while status not in TERMINAL:
            if _now() >= deadline:
                typer.echo(
                    f"timed out after {timeout_min:g} min; run {run_id} keeps going on the server",
                    err=True,
                )
                _emit(json_out, run_id, status, url, base_id)
                raise typer.Exit(3)
            _sleep(POLL_S)
            try:
                run = api.get(f"/v1/runs/{run_id}")
            except ApiFailure as e:
                typer.echo(str(e), err=True)
                if e.status and e.status < 500:
                    raise typer.Exit(3) from e
                continue  # transient server trouble: keep polling until the deadline
            status = run["status"]
            line = f"{status}: {_progress(run)}"
            if line != last:
                typer.echo(line, err=True)
                last = line
    _emit(json_out, run_id, status, url, base_id)
    if status in ("cancelled", "failed"):
        typer.echo(f"run ended {status}", err=True)
        raise typer.Exit(3)


def _emit(json_out: bool, run_id: str, status: str, url: str, baseline: str | None) -> None:
    if json_out:
        typer.echo(
            json.dumps({"run_id": run_id, "status": status, "url": url, "baseline": baseline})
        )
    else:
        typer.echo(f"run: {run_id}\nstatus: {status}\nurl: {url}")
