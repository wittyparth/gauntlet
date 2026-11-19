"""Linter rules (part)."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from typing import Any

from gauntlet_core.checks.detectors.secret import detect_secret, shannon_entropy

from .lint_common import (
    _CONFIRM_KEYS,
    _CONFIRM_PARAMS,
    _DESTRUCTIVE,
    _LLM_CALL,
    _PROMPT_NAME,
    _REFUSAL,
    _SCOPE_CTX,
    _SECRET_NAME,
    _URL_SCOPES,
    _WRITE_SCOPE,
    BROAD_SCOPES,
    _dotted,
    _f,
    _funcs,
    _names_in,
    _src,
    _str_value,
    _target_names,
)
from .types import ScanFinding


def _scope_literals(tree: ast.AST) -> Iterator[tuple[ast.Constant, str]]:
    for node in ast.walk(tree):
        names = _target_names(node)
        subtree: list[ast.AST] = []
        if names and any(_SCOPE_CTX.search(n) for n in names):
            subtree.append(getattr(node, "value", node))
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values, strict=True):
                if (
                    isinstance(k, ast.Constant)
                    and isinstance(k.value, str)
                    and _SCOPE_CTX.search(k.value)
                ):
                    subtree.append(v)
        if isinstance(node, ast.keyword) and node.arg and _SCOPE_CTX.search(node.arg):
            subtree.append(node.value)
        for st in subtree:
            for c in ast.walk(st):
                if isinstance(c, ast.Constant) and isinstance(c.value, str):
                    yield c, c.value


def scopes_in(value: str) -> list[str]:
    return [t for t in re.split(r"[\s,]+", value.strip()) if t]


def _lint_007(tree: ast.AST, path: str) -> list[ScanFinding]:
    out: list[ScanFinding] = []
    seen: set[int] = set()
    file_scopes: list[str] = []
    for c, val in _scope_literals(tree):
        file_scopes += scopes_in(val)
        for tok in scopes_in(val):
            if tok in BROAD_SCOPES and id(c) not in seen:
                seen.add(id(c))
                out.append(_f("LINT-007", "medium", f"broad scope {tok!r}", path, c, tok))
    for c in (
        n for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ):
        if id(c) not in seen and any(t in _URL_SCOPES for t in scopes_in(str(c.value))):
            seen.add(id(c))
            out.append(_f("LINT-007", "medium", "broad scope", path, c, str(c.value)))
    if "offline_access" in file_scopes and any(_WRITE_SCOPE.search(s) for s in file_scopes):
        out.append(
            _f(
                "LINT-007",
                "medium",
                "offline_access together with a write scope",
                path,
                1,
                "offline_access",
            )
        )
    return out


def _lint_009(tree: ast.AST, path: str) -> list[ScanFinding]:
    out: list[ScanFinding] = []
    for node in ast.walk(tree):
        for name in _target_names(node):
            val = getattr(node, "value", None)
            text = _str_value(val) if val is not None else None
            if text and len(text) > 200 and _PROMPT_NAME.search(name) and not _REFUSAL.search(text):
                out.append(
                    _f(
                        "LINT-009",
                        "low",
                        f"{name!r} has no refusal or escalation rule",
                        path,
                        node,
                        text[:60],
                    )
                )
    return out


def _lint_010(tree: ast.AST, path: str) -> list[ScanFinding]:
    out: list[ScanFinding] = []
    scopes: list[ast.AST] = [tree, *_funcs(tree)]
    for scope in scopes:
        tainted: set[str] = set()
        body = list(ast.walk(scope)) if scope is not tree else [n for n in ast.walk(tree)]
        for _ in range(3):
            for node in body:
                if isinstance(node, ast.Assign):
                    llm = any(
                        isinstance(c, ast.Call)
                        and _LLM_CALL.search(_dotted(c.func))
                        and _MODEL_CALL_HINT(_dotted(c.func))
                        for c in ast.walk(node.value)
                    )
                    if llm or _names_in(node.value) & tainted:
                        tainted |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        for c in body:
            if (
                isinstance(c, ast.Call)
                and _dotted(c.func) in {"eval", "exec", "compile"}
                and c.args
                and _names_in(c.args[0]) & tainted
            ):
                out.append(
                    _f(
                        "LINT-010",
                        "high",
                        f"{_dotted(c.func)}() of model output",
                        path,
                        c,
                        _src(c),
                    )
                )
    seen: set[tuple[str, str]] = set()
    uniq = []
    for f in out:
        if (f.rule_id, f.location) not in seen:
            seen.add((f.rule_id, f.location))
            uniq.append(f)
    return uniq


def _MODEL_CALL_HINT(dotted: str) -> bool:
    return bool(
        re.search(r"(?i)completion|messages\.create|responses\.create|invoke|generate", dotted)
    )


def scalar_findings(value: str, path: str, line: int, key: str) -> list[ScanFinding]:
    """LINT-007 and LINT-011 over one config scalar (`key` is the dotted key path)."""
    out: list[ScanFinding] = []
    hits = detect_secret(value)
    if hits:
        out.append(
            _f(
                "LINT-011",
                "high",
                f"{hits[0].label} at {key}",
                path,
                line,
                hits[0].quote[:12] + "...",
            )
        )
    elif (
        _SECRET_NAME.search(key.rsplit(".", 1)[-1])
        and len(value) >= 16
        and " " not in value
        and shannon_entropy(value) >= 3.5
    ):
        out.append(_f("LINT-011", "high", f"high-entropy value at {key}", path, line, key))
    if _SCOPE_CTX.search(key) or any(t in _URL_SCOPES for t in scopes_in(value)):
        for tok in scopes_in(value):
            if tok in BROAD_SCOPES:
                out.append(
                    _f("LINT-007", "medium", f"broad scope {tok!r} at {key}", path, line, tok)
                )
    return out


def tool_entry_findings(entry: dict[str, Any], path: str, line: int) -> list[ScanFinding]:
    """LINT-001 for a tool entry of a tools YAML/JSON file."""
    name = str(entry.get("name", ""))
    desc = str(entry.get("description", ""))
    params = entry.get("parameters") or entry.get("inputSchema") or entry.get("input_schema") or {}
    prop_names = set((params.get("properties") or {}).keys()) if isinstance(params, dict) else set()
    if (
        _DESTRUCTIVE.search(f"{name} {desc}")
        and not prop_names & _CONFIRM_PARAMS
        and not _CONFIRM_KEYS & set(entry)
    ):
        return [_f("LINT-001", "high", f"tool {name!r} has no confirmation step", path, line, name)]
    return []
