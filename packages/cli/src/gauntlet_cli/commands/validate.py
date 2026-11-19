"""`gauntlet validate`: packs, scenario files and agent files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml
from gauntlet_core.packs import PackError, load_pack
from gauntlet_core.schema import Scenario
from gauntlet_core.validate import Issue, validate_pack, validate_scenario
from pydantic import ValidationError

from ..agentfile import AgentFile


def _pack_error_issues(e: PackError, base: Path) -> list[Issue]:
    out = []
    for raw in e.issues:
        path, _, msg = raw.partition(": ")
        out.append(Issue("pack_error", msg or raw, str(base / path) if msg else str(base)))
    return out


def _find_pack_root(path: Path) -> Path | None:
    for parent in path.resolve().parents:
        if (parent / "pack.yaml").is_file():
            return parent
    return None


def validate_path(path: Path) -> list[Issue]:
    if path.is_dir():
        try:
            pack = load_pack(path)
        except PackError as e:
            return _pack_error_issues(e, path)
        return [Issue(i.code, i.message, str(path / i.path)) for i in validate_pack(pack)]
    try:
        data: Any = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as e:
        return [Issue("unreadable", str(e).splitlines()[0], str(path))]
    if not isinstance(data, dict):
        return [Issue("unrecognised_file", "expected a YAML mapping", str(path))]
    root: Path | None = None
    try:
        if "target" in data:
            AgentFile.model_validate(data)
            return []
        if "goal" in data:
            scn = Scenario.model_validate(data)
            root = _find_pack_root(path)
            if root is None:
                return []
            pack = load_pack(root)
            return [
                Issue(i.code, i.message, str(path))
                for i in validate_scenario(
                    scn, pack.world, persona_ids=set(pack.personas), rubric_ids=_rubric_ids()
                )
            ]
    except ValidationError as e:
        return [Issue("schema", str(e).splitlines()[0] + " " + str(e).splitlines()[1], str(path))]
    except PackError as e:
        return _pack_error_issues(e, root or path)
    return [Issue("unrecognised_file", "not a pack, scenario or agent file", str(path))]


def _rubric_ids() -> set[str]:
    from gauntlet_core.eval import load_rubrics

    return set(load_rubrics())


def validate(
    path: Annotated[Path, typer.Argument(help="A pack directory, scenario YAML or agent file.")],
    json_out: Annotated[bool, typer.Option("--json", help="Print issues as JSON.")] = False,
) -> None:
    """Validate PATH. Prints `path:code:message` lines. Exit 0 clean, 2 on any issue."""
    if not path.exists():
        typer.echo(f"{path}:not_found:no such file or directory", err=True)
        raise typer.Exit(2)
    issues = validate_path(path)
    if json_out:
        typer.echo(
            json.dumps([{"path": i.path, "code": i.code, "message": i.message} for i in issues])
        )
    else:
        for i in issues:
            typer.echo(i.line())
    raise typer.Exit(2 if issues else 0)
