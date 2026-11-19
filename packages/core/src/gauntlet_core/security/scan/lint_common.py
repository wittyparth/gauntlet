"""Linter rules LINT-001..LINT-011 over Python source (`ast`) and config scalars.

Heuristics, not proofs: each rule is conservative about what it flags and reports the line.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator

from .types import ScanFinding, Severity, excerpt

__all__ = ["BROAD_SCOPES", "LINT_RULES"]

LINT_RULES: dict[str, tuple[str, str]] = {
    "LINT-001": ("Destructive or financial tool without a confirmation step", "excessive_agency"),
    "LINT-002": ("Secret in a prompt or credential-named literal", "data_disclosure"),
    "LINT-003": ("Unbounded agent loop", "resource_abuse"),
    "LINT-004": ("Network or client call without a timeout", "resource_abuse"),
    "LINT-005": ("Tool argument reaches a dangerous sink unvalidated", "tool_injection"),
    "LINT-006": ("Untrusted content flows into a prompt without separation", "indirect_injection"),
    "LINT-007": ("Over-broad OAuth or API scope", "excessive_agency"),
    "LINT-008": ("Model call without an output cap", "resource_abuse"),
    "LINT-009": ("Prompt has no refusal or escalation rule", "excessive_agency"),
    "LINT-010": ("eval or exec of model output", "tool_injection"),
    "LINT-011": ("Hard-coded credential", "data_disclosure"),
}
# Verified against the providers' scope documentation (Google OAuth scopes, GitHub OAuth scopes,
# Microsoft Graph permissions) on 2026-11-20; entries are exact strings.
BROAD_SCOPES = frozenset({
    "*", "https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/gmail.modify",
    "https://mail.google.com/", "repo", "admin:org", "admin:repo_hook",
    "Directory.ReadWrite.All", "Mail.ReadWrite", "Files.ReadWrite.All",
})  # fmt: skip
_URL_SCOPES = frozenset(s for s in BROAD_SCOPES if s.startswith("https://"))
_WRITE_SCOPE = re.compile(r"(?i)write|modify|\.all\b|full_access|manage")

_DESTRUCTIVE = re.compile(r"(?i)delete|drop|remove|refund|transfer|pay|send|exec")
_CONFIRM_PARAMS = {"confirm", "approval", "confirmed"}
_CONFIRM_KEYS = {"require_approval", "needs_confirmation"}
_PROMPT_NAME = re.compile(r"(?i)prompt|instruction|system")
_SECRET_NAME = re.compile(r"(?i)key|token|secret|password")
_REFUSAL = re.compile(r"(?i)refuse|decline|cannot|not allowed|escalate|hand off|human")
_LOOP_CALL = re.compile(r"(?i)completion|chat|invoke|run|generate|create")
_BOUND_NAME = re.compile(r"(?i)iter|step|count|attempt|turn|max|limit|budget|tries|retr|remaining")
_HTTP_VERBS = {"get", "post", "put", "delete", "request", "head", "patch"}
_CLIENT_CTORS = {"OpenAI", "AsyncOpenAI", "Anthropic", "AsyncAnthropic", "AzureOpenAI"}
_FETCHERS = re.compile(r"(?i)fetch|browse|read_email|search|scrape|get_page|load_url|read_inbox")
_DELIMS = ("```", "<", "---", "###", '"""', "BEGIN")
_CAP_KW = {"max_tokens", "max_output_tokens", "max_completion_tokens", "max_new_tokens"}
_MODEL_CALL = re.compile(
    r"(chat\.completions\.create|messages\.create|responses\.create|litellm\.a?completion)$"
)
_LLM_CALL = re.compile(r"(?i)(completions?|messages|responses|chat|invoke|generate)\b")
_AGENT_CLASSES = {"AgentExecutor", "initialize_agent"}
_SCOPE_CTX = re.compile(r"(?i)scopes?|permissions?")
_TOOL_DECORATORS = {"tool", "function_tool"}


def _f(
    rule: str, sev: Severity, detail: str, path: str, node: ast.AST | int, ev: str
) -> ScanFinding:
    title, cat = LINT_RULES[rule]
    line = node if isinstance(node, int) else getattr(node, "lineno", 1)
    return ScanFinding(rule, sev, title, detail, f"{path}:{line}", excerpt(ev), cat)


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return _dotted(node.func)
    return ""


def _src(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - defensive
        return ""


def _names_in(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _str_value(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str)
        )
    return None


def _target_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Assign):
        return [t.id for t in node.targets if isinstance(t, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return []


def _funcs(tree: ast.AST) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef):
            yield n


def _is_tool(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(_dotted(d).split(".")[-1] in _TOOL_DECORATORS for d in fn.decorator_list)


def _decorator_kwargs(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    return {
        kw.arg for d in fn.decorator_list if isinstance(d, ast.Call) for kw in d.keywords if kw.arg
    }
