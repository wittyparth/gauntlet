"""Scenario packs on disk: `<root>/packs/<id>/{pack.yaml, world.yaml, policy.md, scenarios/,
suites/}`. `load_pack` puts `<root>` on `sys.path` when the pack sits in a `packs` package so
`packs.<id>.handlers:fn` entrypoints import."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from gauntlet_core.schema import Persona, Scenario, Suite, WorldSpec, load_yaml
from gauntlet_core.sim import load_persona_library

__all__ = ["Pack", "PackError", "load_pack"]


class PackError(ValueError):
    """The pack directory is malformed. `issues` lists `file: problem` strings."""

    def __init__(self, issues: list[str]) -> None:
        super().__init__("; ".join(issues))
        self.issues = issues


@dataclass(frozen=True)
class Pack:
    id: str
    title: str
    version: int
    world: WorldSpec
    scenarios: dict[str, Scenario]
    suites: dict[str, Suite]
    personas: dict[str, Persona]
    policy_text: str
    root: Path


def _load_dir(path: Path, model: type, issues: list[str]) -> list:
    out = []
    if not path.is_dir():
        return out
    for f in sorted(path.glob("*.yaml")):
        try:
            out.append(load_yaml(model, f))
        except (ValidationError, yaml.YAMLError) as e:
            issues.append(f"{f.relative_to(path.parent)}: {str(e).splitlines()[0]}")
    return out


def load_pack(path: Path) -> Pack:
    path = Path(path).resolve()
    manifest_path = path / "pack.yaml"
    if not manifest_path.is_file():
        raise PackError([f"{path}: no pack.yaml"])
    manifest = yaml.safe_load(manifest_path.read_text()) or {}
    issues: list[str] = []
    if path.parent.name == "packs" and (path.parent / "__init__.py").is_file():
        root = str(path.parent.parent)
        if root not in sys.path:
            sys.path.insert(0, root)
    try:
        world = load_yaml(WorldSpec, path / manifest.get("world", "world.yaml"))
    except (ValidationError, yaml.YAMLError, OSError) as e:
        raise PackError([f"world: {str(e).splitlines()[0]}"]) from e
    library = load_persona_library()
    personas: dict[str, Persona] = {}
    for pid in manifest.get("personas", []):
        if pid in library:
            personas[pid] = library[pid]
        else:
            issues.append(f"pack.yaml: unknown persona {pid!r}")
    scenarios: dict[str, Scenario] = {}
    for scn in _load_dir(path / "scenarios", Scenario, issues):
        if scn.id in scenarios:
            issues.append(f"scenarios: duplicate scenario id {scn.id!r}")
        scenarios[scn.id] = scn
        if isinstance(scn.world, str) and scn.world != world.id:
            issues.append(f"scenarios/{scn.id}: world {scn.world!r} is not the pack world")
    suites = {s.id: s for s in _load_dir(path / "suites", Suite, issues)}
    policy_file = manifest.get("policy")
    policy = (
        (path / policy_file).read_text() if policy_file and (path / policy_file).is_file() else ""
    )
    if issues:
        raise PackError(issues)
    return Pack(
        id=str(manifest.get("id", path.name)),
        title=str(manifest.get("title", path.name)),
        version=int(manifest.get("version", 1)),
        world=world,
        scenarios=scenarios,
        suites=suites,
        personas=personas,
        policy_text=policy,
        root=path,
    )
