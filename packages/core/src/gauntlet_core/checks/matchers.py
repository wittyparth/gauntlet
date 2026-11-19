"""Path resolution and matcher evaluation (contracts section 4).

Paths are dotted, with `[*]` for any list element and `[n]` for an index. A path can lead to
zero, one or many values; a matcher holds when it holds for any of them (or, for an empty
result, when it holds for an absent value).
"""

from __future__ import annotations

import functools
import importlib
import operator
import re
from collections.abc import Callable
from typing import Any

from gauntlet_core.schema import Matcher

MAX_PATTERN = 1000
MAX_TEXT = 200_000


class _Unresolved:
    def __repr__(self) -> str:
        return "UNRESOLVED"


UNRESOLVED: Any = _Unresolved()
_MISSING: Any = object()
_TOKEN = re.compile(r"\[(\*|\d+)\]|([^.\[\]]+)")

try:  # regexes are user supplied: prefer the linear-time engine when it is installed
    _engine: Any = importlib.import_module("re2")
except ImportError:  # pragma: no cover - depends on the environment
    _engine = re


def resolve_path(obj: Any, path: str) -> list[Any]:
    """All values `path` reaches in `obj`. Missing keys and out-of-range indexes give []."""
    current: list[Any] = [obj]
    for index, name in _TOKEN.findall(path):
        nxt: list[Any] = []
        for node in current:
            if name:
                if isinstance(node, dict):
                    if name in node:
                        nxt.append(node[name])
                elif isinstance(node, list) and name.isdigit() and int(name) < len(node):
                    nxt.append(node[int(name)])
            elif isinstance(node, list):
                if index == "*":
                    nxt.extend(node)
                elif int(index) < len(node):
                    nxt.append(node[int(index)])
        current = nxt
    return current


def _num(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


@functools.lru_cache(maxsize=512)
def _compile(pattern: str) -> Any:
    if len(pattern) > MAX_PATTERN:
        return None
    try:
        return _engine.compile(pattern)
    except Exception:
        return None


def _regex(pattern: str, value: Any) -> bool:
    if not isinstance(value, str):
        return False
    compiled = _compile(pattern)
    return compiled is not None and compiled.search(value[:MAX_TEXT]) is not None


def _contains(container: Any, item: Any) -> bool:
    if isinstance(container, str):
        return isinstance(item, str) and item in container
    if isinstance(container, list | tuple | dict):
        return item in container
    return False


_CMP: dict[str, Callable[[Any, Any], bool]] = {
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
}


def compare(op: str, left: Any, right: Any) -> bool:
    if op == "eq":
        return bool(left == right)
    if op == "ne":
        return bool(left != right)
    return _num(left) and _num(right) and _CMP[op](left, right)


def match_value(
    m: Matcher, value: Any, *, present: bool = True, ref_value: Any = UNRESOLVED
) -> bool:
    """Every operator set on `m` must hold. `present=False` models an absent value: only
    `exists: false` and `ne` can hold. An unresolved `ref` never matches."""
    v = value if present else _MISSING
    fields = m.model_fields_set
    if "exists" in fields and (m.exists is not None) and m.exists != present:
        return False
    if "eq" in fields and not (present and value == m.eq):
        return False
    if "ne" in fields and present and value == m.ne:
        return False
    if m.in_ is not None and not (present and value in m.in_):
        return False
    if m.regex is not None and not (present and _regex(m.regex, value)):
        return False
    if "contains" in fields and not (present and _contains(value, m.contains)):
        return False
    for op in ("gt", "gte", "lt", "lte"):
        bound = getattr(m, op)
        if bound is not None and not (present and _num(value) and _CMP[op](value, bound)):
            return False
    if m.ref is not None:
        if ref_value is UNRESOLVED:
            return False
        if m.ref_op == "ne" and not present:
            return True
        if not (present and compare(m.ref_op, v, ref_value)):
            return False
    return True
