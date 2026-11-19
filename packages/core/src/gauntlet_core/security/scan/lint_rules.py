"""Linter rules (part)."""

from __future__ import annotations

import ast
from collections.abc import Callable

from gauntlet_core.checks.detectors.secret import detect_secret, shannon_entropy

from .lint_common import (
    _AGENT_CLASSES,
    _BOUND_NAME,
    _CAP_KW,
    _CLIENT_CTORS,
    _CONFIRM_KEYS,
    _CONFIRM_PARAMS,
    _DELIMS,
    _DESTRUCTIVE,
    _FETCHERS,
    _HTTP_VERBS,
    _LOOP_CALL,
    _MODEL_CALL,
    _PROMPT_NAME,
    _SECRET_NAME,
    _decorator_kwargs,
    _dotted,
    _f,
    _funcs,
    _is_tool,
    _names_in,
    _src,
    _str_value,
    _target_names,
)
from .lint_flow import (
    _lint_007,
    _lint_009,
    _lint_010,
)
from .types import ScanFinding


def _lint_001(tree: ast.AST, path: str) -> list[ScanFinding]:
    out: list[ScanFinding] = []
    for fn in _funcs(tree):
        if not _is_tool(fn):
            continue
        text = f"{fn.name} {ast.get_docstring(fn) or ''}"
        params = {a.arg for a in [*fn.args.args, *fn.args.kwonlyargs]}
        if (
            _DESTRUCTIVE.search(text)
            and not params & _CONFIRM_PARAMS
            and not _decorator_kwargs(fn) & _CONFIRM_KEYS
        ):
            out.append(
                _f(
                    "LINT-001",
                    "high",
                    f"tool {fn.name!r} has no confirmation step",
                    path,
                    fn,
                    fn.name,
                )
            )
    for d in (n for n in ast.walk(tree) if isinstance(n, ast.Dict)):
        out += _tool_dict(d, path)
    return out


def _tool_dict(d: ast.Dict, path: str) -> list[ScanFinding]:
    """OpenAI-format tool dicts: `{"type": "function", "function": {name, ...}}`."""
    keys = {k.value: v for k, v in zip(d.keys, d.values, strict=True)
            if isinstance(k, ast.Constant) and isinstance(k.value, str)}  # fmt: skip
    fn = keys.get("function")
    if not (
        _str_value(keys.get("type", ast.Constant(None))) == "function" and isinstance(fn, ast.Dict)
    ):
        return []
    f = {k.value: v for k, v in zip(fn.keys, fn.values, strict=True)
         if isinstance(k, ast.Constant) and isinstance(k.value, str)}  # fmt: skip
    name = _str_value(f.get("name", ast.Constant(""))) or ""
    desc = _str_value(f.get("description", ast.Constant(""))) or ""
    if not _DESTRUCTIVE.search(f"{name} {desc}") or _CONFIRM_KEYS & set(f):
        return []
    params = {n.value for n in ast.walk(f.get("parameters", ast.Constant(None)))
              if isinstance(n, ast.Constant) and isinstance(n.value, str)}  # fmt: skip
    if params & _CONFIRM_PARAMS:
        return []
    return [_f("LINT-001", "high", f"tool {name!r} has no confirmation step", path, d, name)]


def _lint_002_011(tree: ast.AST, path: str) -> list[ScanFinding]:
    out: list[ScanFinding] = []
    lines002: set[int] = set()
    for node in ast.walk(tree):
        for name in _target_names(node):
            val = getattr(node, "value", None)
            text = _str_value(val) if val is not None else None
            if not text:
                continue
            hit = detect_secret(text) if _PROMPT_NAME.search(name) else []
            token = (
                _SECRET_NAME.search(name)
                and len(text) >= 16
                and " " not in text
                and shannon_entropy(text) >= 3.5
            )
            if hit or token:
                lines002.add(getattr(node, "lineno", 0))
                out.append(
                    _f(
                        "LINT-002",
                        "high",
                        f"secret-like value assigned to {name!r}",
                        path,
                        node,
                        text[:20] + "...",
                    )
                )
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.lineno not in lines002:
            hits = detect_secret(n.value)
            if hits:
                out.append(
                    _f(
                        "LINT-011",
                        "high",
                        f"{hits[0].label} literal",
                        path,
                        n,
                        hits[0].quote[:12] + "...",
                    )
                )
                lines002.add(n.lineno)
    return out


def _lint_003(tree: ast.AST, path: str) -> list[ScanFinding]:
    out: list[ScanFinding] = []
    for w in (n for n in ast.walk(tree) if isinstance(n, ast.While)):
        unbounded = (isinstance(w.test, ast.Constant) and w.test.value is True) or (
            isinstance(w.test, ast.UnaryOp)
            and isinstance(w.test.op, ast.Not)
            and isinstance(w.test.operand, ast.Name)
            and w.test.operand.id in {"done", "finished", "complete"}
        )
        if not unbounded:
            continue
        calls = [c for c in ast.walk(w) if isinstance(c, ast.Call)]
        if not any(_LOOP_CALL.search(_dotted(c.func).split(".")[-1]) for c in calls):
            continue
        bounded = False
        counters = {
            a.target.id
            for a in ast.walk(w)
            if isinstance(a, ast.AugAssign) and isinstance(a.target, ast.Name)
        }
        for iff in (n for n in ast.walk(w) if isinstance(n, ast.If)):
            guard = any(
                isinstance(n, ast.Compare)
                and any(
                    x in counters or _BOUND_NAME.search(x)
                    for x in _names_in(n)
                    | {a.attr for a in ast.walk(n) if isinstance(a, ast.Attribute)}
                )
                for n in ast.walk(iff.test)
            )
            exits = any(
                isinstance(n, ast.Break | ast.Return) for s in iff.body for n in ast.walk(s)
            )
            bounded = bounded or (guard and exits)
        if not bounded:
            out.append(
                _f(
                    "LINT-003",
                    "medium",
                    "loop calls a model with no iteration bound",
                    path,
                    w,
                    "while ...",
                )
            )
    for c in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
        if _dotted(c.func).split(".")[-1] in _AGENT_CLASSES:
            for kw in c.keywords:
                if (
                    kw.arg == "max_iterations"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is None
                ):
                    out.append(_f("LINT-003", "medium", "max_iterations=None", path, c, _src(c)))
    return out


def _lint_004_008(tree: ast.AST, path: str) -> list[ScanFinding]:
    out: list[ScanFinding] = []
    for c in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
        dotted = _dotted(c.func)
        kws = {k.arg for k in c.keywords}
        spread = None in kws
        last = dotted.split(".")[-1]
        head = dotted.split(".")[0]
        http = head in {"requests", "httpx"} and last in _HTTP_VERBS and dotted.count(".") == 1
        other = (
            dotted in {"urllib.request.urlopen", "aiohttp.ClientSession"} or last in _CLIENT_CTORS
        )
        session = head in {"session", "client"} and last in _HTTP_VERBS and "aiohttp" in path
        if (http or other or session) and "timeout" not in kws and not spread:
            out.append(_f("LINT-004", "medium", f"{dotted}() has no timeout", path, c, _src(c)))
        if _MODEL_CALL.search(dotted) and not (_CAP_KW & kws) and not spread:
            out.append(_f("LINT-008", "low", f"{dotted}() has no output cap", path, c, _src(c)))
    return out


def _tainted_from_params(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    tainted = {a.arg for a in [*fn.args.args, *fn.args.kwonlyargs] if a.arg not in {"self", "cls"}}
    for _ in range(3):
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign) and _names_in(node.value) & tainted:
                tainted |= {t.id for t in node.targets if isinstance(t, ast.Name)}
    return tainted


def _formatted(node: ast.AST) -> bool:
    return isinstance(node, ast.JoinedStr | ast.BinOp) or (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "format"
    )


def _lint_005(tree: ast.AST, path: str) -> list[ScanFinding]:
    out: list[ScanFinding] = []
    for fn in _funcs(tree):
        if not _is_tool(fn):
            continue
        tainted = _tainted_from_params(fn)
        for c in (n for n in ast.walk(fn) if isinstance(n, ast.Call)):
            d = _dotted(c.func)
            args = [*c.args, *(k.value for k in c.keywords)]
            hit = False
            if d.startswith("subprocess.") or d in {"os.system", "eval", "exec"}:
                hit = any(_names_in(a) & tainted for a in args)
            elif d == "open" and c.args:
                hit = bool(_names_in(c.args[0]) & tainted)
            elif d.endswith(".execute") and c.args:
                hit = _formatted(c.args[0]) and bool(_names_in(c.args[0]) & tainted)
            if hit:
                out.append(_f("LINT-005", "high", f"tool argument reaches {d}()", path, c, _src(c)))
    return out


def _lint_006(tree: ast.AST, path: str) -> list[ScanFinding]:
    out: list[ScanFinding] = []
    for fn in _funcs(tree):
        fetched: set[str] = set()
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call | ast.Await):
                call = node.value.value if isinstance(node.value, ast.Await) else node.value
                if isinstance(call, ast.Call) and _FETCHERS.search(_dotted(call.func)):
                    fetched |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        if not fetched:
            continue
        for js in (n for n in ast.walk(fn) if isinstance(n, ast.JoinedStr)):
            if not _names_in(js) & fetched:
                continue
            consts = "".join(
                v.value
                for v in js.values
                if isinstance(v, ast.Constant) and isinstance(v.value, str)
            )
            if not any(d in consts for d in _DELIMS):
                out.append(
                    _f(
                        "LINT-006",
                        "medium",
                        "fetched content placed in a prompt with no delimiter (confidence: low)",
                        path,
                        js,
                        _src(js),
                    )
                )
    return out


_RULES: list[Callable[[ast.AST, str], list[ScanFinding]]] = [
    _lint_001, _lint_002_011, _lint_003, _lint_004_008, _lint_005, _lint_006, _lint_007,
    _lint_009, _lint_010,
]  # fmt: skip


def lint_python(source: str, path: str) -> list[ScanFinding]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    out: list[ScanFinding] = []
    for rule in _RULES:
        out += rule(tree, path)
    return out
