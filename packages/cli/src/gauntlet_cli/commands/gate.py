"""`gauntlet gate`: turn a finished run into pass, fail or error against a gates file (P3-4).

Exit codes: 0 passed (warnings allowed), 1 a gate failed, 2 usage or config error, 3 platform
error (incomplete run, run with nothing counted, server trouble)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, Literal

import typer
from gauntlet_core.eval import CompareReport, EpisodeRecord, RunData, RunReport, compare_runs
from gauntlet_core.eval.pr_comment import FindingBrief, render_pr_comment
from gauntlet_core.gates import (
    FindingsDelta,
    GateConfigError,
    GateResult,
    evaluate_gates,
    load_gates,
)
from gauntlet_core.schema import RunManifest

from ..localdb import LocalDb
from .remote import Api, ApiFailure, web_url_for
from .report import find_run_dir

__all__ = ["gate"]

EXIT = {"pass": 0, "fail": 1, "error": 3}


def _usage(msg: str) -> typer.Exit:
    typer.echo(msg, err=True)
    return typer.Exit(2)


def _local_data(run_dir: Path) -> tuple[RunData, str]:
    report = RunReport.model_validate_json((run_dir / "report.json").read_text())
    meta = json.loads((run_dir / "meta.json").read_text())
    manifest = RunManifest.model_validate(meta["manifest"])
    db = LocalDb(run_dir / "local.db")
    try:
        status = db.status(report.run_id) or "done"
        records = [
            EpisodeRecord(
                e.id, e.scenario_id, e.rep, e.outcome or "platform_error", e.termination,
                e.cost_usd_micros, e.latency_ms, e.world_fidelity, e.reasons,
            )
            for e in db.episodes(report.run_id)
        ]  # fmt: skip
    finally:
        db.close()
    cfg = manifest.agent_version.target
    data = RunData(
        run_id=report.run_id,
        suite_id=manifest.suite_id,
        scenario_versions=dict(manifest.scenario_versions),
        records=records,
        report=report,
        agent_label=manifest.agent_version.label,
        model=getattr(cfg, "model", None),
        repetitions=manifest.repetitions,
        judge_model=manifest.model_roles.get("judge_small"),
        agent_id=manifest.agent_version.agent_id,
    )
    return data, status


def _load_local(run_dir: Path, baseline: str | None) -> tuple[RunReport, str, CompareReport | None]:
    try:
        data, status = _local_data(run_dir)
    except (OSError, ValueError, KeyError) as e:
        raise _usage(f"{run_dir}: not a usable run directory: {e}") from e
    compare = None
    if baseline:
        base_dir = find_run_dir(baseline)
        if base_dir is None:
            raise _usage(f"baseline {baseline!r} is not a local run directory")
        try:
            base, _ = _local_data(base_dir)
        except (OSError, ValueError, KeyError) as e:
            raise _usage(f"{base_dir}: not a usable run directory: {e}") from e
        compare = compare_runs(base, data)
    return data.report, status, compare


def _load_remote(
    run_id: str, baseline: str | None, api: Api
) -> tuple[RunReport, str, CompareReport | None, FindingsDelta | None, list[FindingBrief]]:
    run = api.get(f"/v1/runs/{run_id}")
    report = RunReport.model_validate(api.get(f"/v1/runs/{run_id}/report"))
    base_id = baseline or run.get("baseline_of")
    compare = delta = None
    briefs: list[FindingBrief] = []
    if base_id and run["status"] == "done":
        compare = CompareReport.model_validate(
            api.get(f"/v1/runs/{run_id}/compare", baseline=base_id)
        )
        try:
            raw = api.get(f"/v1/runs/{run_id}/findings-delta", baseline=base_id)
            delta = FindingsDelta(new_by_severity=raw["new_by_severity"])
            briefs = [FindingBrief(f["title"], f["severity"], f["category"]) for f in raw["new"]]
        except ApiFailure as e:
            if e.status != 404:
                raise
    return report, run["status"], compare, delta, briefs


def _text(res: GateResult) -> str:
    lines = [f"gate: {res.status.upper()}"]
    for g in res.gates:
        extra = []
        if g.value is not None:
            extra.append(f"value {g.value:.4g}" if isinstance(g.value, float) else f"{g.value}")
        if g.threshold is not None:
            thr = g.threshold
            extra.append(f"threshold {thr:.4g}" if isinstance(thr, float) else f"{thr}")
        if g.detail:
            extra.append(g.detail)
        lines.append(f"  {g.status:<5} {g.id}" + (f"  ({'; '.join(extra)})" if extra else ""))
    return "\n".join(lines)


def gate(
    run: Annotated[str, typer.Option("--run", help="Run id (server) or local run directory.")],
    baseline: Annotated[
        str | None, typer.Option("--baseline", help="Baseline run id or directory.")
    ] = None,
    gates: Annotated[
        Path | None, typer.Option("--gates", help="Gates YAML (default: built-in defaults).")
    ] = None,
    api_url: Annotated[
        str, typer.Option("--api-url", envvar="GAUNTLET_API_URL", help="Gauntlet server url.")
    ] = "http://localhost:8000",
    api_key: Annotated[
        str | None, typer.Option("--api-key", envvar="GAUNTLET_API_KEY", help="API key.")
    ] = None,
    web_url: Annotated[
        str | None, typer.Option("--web-url", help="Web app url when not the api host.")
    ] = None,
    fmt: Annotated[
        Literal["text", "json", "md"], typer.Option("--format", help="text, json or md.")
    ] = "text",
    out: Annotated[
        Path | None, typer.Option("--out", help="Also write the JSON result here.")
    ] = None,
    md_out: Annotated[
        Path | None, typer.Option("--md-out", help="Also write the PR comment markdown here.")
    ] = None,
) -> None:
    """Evaluate the gates in --gates against a run (and its baseline) and exit accordingly."""
    if gates is not None and not gates.is_file():
        raise _usage(f"{gates}: no such gates file")
    try:
        config = load_gates(gates)
    except GateConfigError as e:
        raise _usage(f"gates: {e}") from e

    local = find_run_dir(run)
    compare: CompareReport | None = None
    delta: FindingsDelta | None = None
    briefs: list[FindingBrief] = []
    try:
        if local is not None:
            report, status, compare = _load_local(local, baseline)
            url = str(local)
        else:
            api = Api(api_url, api_key)
            report, status, compare, delta, briefs = _load_remote(run, baseline, api)
            url = f"{web_url_for(api_url, web_url)}/runs/{run}"
    except ApiFailure as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(2 if e.status in (401, 403, 404) else 3) from e

    result = evaluate_gates(config, report, compare, delta, run_status=status)
    payload: dict[str, Any] = result.model_dump(mode="json")
    if out is not None:
        out.write_text(json.dumps(payload, indent=2))
    md = ""
    if md_out is not None or fmt == "md":
        md = render_pr_comment(report, compare, result, url, findings=briefs)
        if md_out is not None:
            md_out.write_text(md)
    if fmt == "json":
        typer.echo(json.dumps(payload, indent=2))
    elif fmt == "md":
        typer.echo(md)
    else:
        typer.echo(_text(result))
    raise typer.Exit(EXIT[result.status])
