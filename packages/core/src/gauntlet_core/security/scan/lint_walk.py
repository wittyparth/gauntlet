"""File discovery, pragma handling and config (YAML/JSON) walking for the linter."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

import yaml

from .lint_flow import scalar_findings, tool_entry_findings
from .lint_rules import lint_python
from .types import ScanFinding

__all__ = ["lint_paths", "lint_text"]

_PRAGMA = re.compile(r"#\s*gauntlet:\s*ignore\[([A-Z0-9,\s-]+)\]")
_SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".mypy_cache", ".ruff_cache"}
_SUFFIXES = {".py", ".yaml", ".yml", ".json"}


def _files(paths: Iterable[Path]) -> Iterator[Path]:
    for p in paths:
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.suffix in _SUFFIXES and not _SKIP_DIRS & set(f.parts):
                    yield f
        elif p.is_file():
            yield p


def _suppressed(finding: ScanFinding, lines: Sequence[str]) -> bool:
    """A pragma on the finding's line or the line above ignores that rule."""
    try:
        line = int(finding.location.rsplit(":", 1)[1])
    except (ValueError, IndexError):
        return False
    for ln in (line, line - 1):
        m = _PRAGMA.search(lines[ln - 1]) if 1 <= ln <= len(lines) else None
        if m and finding.rule_id in {r.strip() for r in m.group(1).split(",")}:
            return True
    return False


def _walk_config(node: yaml.Node, path: str, key: str = "") -> Iterator[ScanFinding]:
    if isinstance(node, yaml.ScalarNode):
        yield from scalar_findings(str(node.value), path, node.start_mark.line + 1, key)
    elif isinstance(node, yaml.MappingNode):
        entry: dict[str, object] = {}
        for k, v in node.value:
            if isinstance(k, yaml.ScalarNode):
                entry[str(k.value)] = _plain(v)
        if "name" in entry and ("description" in entry or "parameters" in entry):
            yield from tool_entry_findings(entry, path, node.start_mark.line + 1)
        for k, v in node.value:
            sub = (
                f"{key}.{k.value}"
                if key and isinstance(k, yaml.ScalarNode)
                else str(getattr(k, "value", ""))
            )
            yield from _walk_config(v, path, sub)
    elif isinstance(node, yaml.SequenceNode):
        for item in node.value:
            yield from _walk_config(item, path, key)


def _plain(node: yaml.Node) -> object:
    try:
        return yaml.safe_load(yaml.serialize(node))
    except yaml.YAMLError:
        return None


def lint_text(path: str, text: str) -> list[ScanFinding]:
    """Findings for one file's text (before pragma and select/ignore filtering)."""
    if path.endswith(".py"):
        return lint_python(text, path)
    try:
        root = yaml.compose(text)
    except yaml.YAMLError:
        return []
    return list(_walk_config(root, path)) if root is not None else []


def lint_paths(
    paths: Sequence[Path | str],
    *,
    select: Sequence[str] = (),
    ignore: Sequence[str] = (),
) -> list[ScanFinding]:
    out: list[ScanFinding] = []
    for f in _files(Path(p) for p in paths):
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lines = text.splitlines()
        for finding in lint_text(str(f), text):
            if select and finding.rule_id not in select:
                continue
            if finding.rule_id in ignore or _suppressed(finding, lines):
                continue
            out.append(finding)
    return sorted(
        out,
        key=lambda x: (x.location.rsplit(":", 1)[0], int(x.location.rsplit(":", 1)[1]), x.rule_id),
    )
