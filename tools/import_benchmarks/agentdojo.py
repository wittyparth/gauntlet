"""AgentDojo suite importer (MIT, ETH SPY Lab). Reads a checkout of the upstream repository:

    <src>/src/agentdojo/data/suites/<suite>/{environment,injection_vector_defaults}.yaml
    <src>/src/agentdojo/default_suites/v1/tools/*.py            (tool docstrings and signatures)
    <src>/src/agentdojo/default_suites/v1/<suite>/{user_tasks,injection_tasks}.py

Suites: `banking` and `slack`. Tool semantics are our reviewed pure ports
(`agentdojo_handlers.py`); names, descriptions and parameters are read from upstream. User tasks
become scenarios whose `success` (the utility check) is derived by replaying the task's
`ground_truth` calls through our handlers: one `state` check per changed record field. Tasks
whose utility is about what the agent says (no state change), whose ground truth is not a literal
list of calls, or that use an unported tool are skipped with a reason. Injection tasks become
`Attack`s whose security `objective` requires the effectful ground-truth calls.
"""

from __future__ import annotations

import ast
import contextlib
import re
from pathlib import Path
from typing import Any

import yaml
from gauntlet_core.schema import Attack, Scenario, WorldSpec

from .common import ImportReport, Reason, replay, require_pin, state_checks, write_yaml

__all__ = ["PIN", "REPO", "SUITES", "import_agentdojo"]

PIN = "0.1.35"
REPO = "https://github.com/ethz-spylab/agentdojo"
HANDLERS = "tools.import_benchmarks.agentdojo_handlers"
SUITES: dict[str, dict[str, Any]] = {
    "banking": {
        "tools": [
            "get_iban", "send_money", "schedule_transaction", "update_scheduled_transaction",
            "get_balance", "get_most_recent_transactions", "get_scheduled_transactions",
            "read_file", "get_user_info", "update_password", "update_user_info",
        ],
        "inject_tool": "read_file",
    },
    "slack": {
        "tools": [
            "get_channels", "add_user_to_channel", "read_channel_messages", "read_inbox",
            "send_direct_message", "send_channel_message", "get_users_in_channel",
            "invite_user_to_slack", "remove_user_from_slack", "get_webpage", "post_webpage",
        ],
        "inject_tool": "read_channel_messages",
    },
}  # fmt: skip
RISK = {
    "send_money": "financial", "schedule_transaction": "financial",
    "update_scheduled_transaction": "financial", "update_password": "write",
    "update_user_info": "write", "add_user_to_channel": "write",
    "send_direct_message": "external_comm", "send_channel_message": "external_comm",
    "invite_user_to_slack": "external_comm", "remove_user_from_slack": "destructive",
    "post_webpage": "external_comm",
}  # fmt: skip
UNTRUSTED = {
    "read_file", "get_most_recent_transactions", "get_scheduled_transactions",
    "read_channel_messages", "read_inbox", "get_webpage",
}  # fmt: skip
EFFECTS = set(RISK)  # tools whose call is the effect of an attack
# free text is not matched exactly; `password` is redacted from journaled arguments
FREE_TEXT = {"subject", "body", "content", "message", "text", "password"}
_TYPES = {"str": "string", "int": "integer", "float": "number", "bool": "boolean"}


class _NotLiteral(Exception):
    pass


def _lit(node: ast.AST, consts: dict[str, Any]) -> Any:
    """Literal evaluation extended with class/module constants, `self.X` and f-strings."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name) and node.id in consts:
        return consts[node.id]
    if (
        isinstance(node, ast.Attribute)
        and getattr(node.value, "id", "") == "self"
        and node.attr in consts
    ):
        return consts[node.attr]
    if isinstance(node, ast.Dict):
        return {
            _lit(k, consts): _lit(v, consts)
            for k, v in zip(node.keys, node.values, strict=False)
            if k
        }
    if isinstance(node, ast.List | ast.Tuple):
        return [_lit(e, consts) for e in node.elts]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _lit(node.left, consts) + _lit(node.right, consts)
    if isinstance(node, ast.JoinedStr):
        return "".join(
            str(_lit(p.value, consts)) if isinstance(p, ast.FormattedValue) else str(p.value)
            for p in node.values
            if isinstance(p, ast.FormattedValue | ast.Constant)
        )
    raise _NotLiteral(ast.dump(node)[:60])


def _consts(body: list[ast.stmt], base: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for st in body:
        if (
            isinstance(st, ast.Assign)
            and len(st.targets) == 1
            and isinstance(st.targets[0], ast.Name)
        ):
            with contextlib.suppress(_NotLiteral):
                out[st.targets[0].id] = _lit(st.value, out)
    return out


def read_task_classes(path: Path) -> list[dict[str, Any]]:
    """`{class, text, calls, error}` for every class with PROMPT or GOAL, in source order.
    `calls` is None when the ground truth is not a literal list of `FunctionCall`s."""
    tree = ast.parse(path.read_text())
    module = _consts(tree.body, {})
    out = []
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
        consts = _consts(cls.body, module)
        text = consts.get("PROMPT", consts.get("GOAL"))
        if not isinstance(text, str):
            continue
        calls: list[tuple[str, dict[str, Any]]] | None = None
        error = ""
        for fn in (n for n in cls.body if isinstance(n, ast.FunctionDef)):
            if fn.name != "ground_truth":
                continue
            try:
                calls = []
                found = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
                for c in sorted(found, key=lambda n: (n.lineno, n.col_offset)):
                    if getattr(c.func, "id", "") != "FunctionCall":
                        continue
                    kws = {k.arg: k.value for k in c.keywords}
                    args = _lit(kws["args"], consts) if "args" in kws else {}
                    calls.append((str(_lit(kws["function"], consts)), args))
            except (_NotLiteral, KeyError):
                calls, error = None, "ground_truth_not_literal"
        out.append(
            {
                "class": cls.name,
                "text": text,
                "calls": calls,
                "error": error or ("no_ground_truth" if calls is None else ""),
            }
        )
    return out


def read_tool_specs(tools_dir: Path, names: list[str]) -> dict[str, dict[str, Any]]:
    """`name -> {description, parameters}` from upstream docstrings and signatures."""
    specs: dict[str, dict[str, Any]] = {}
    for f in sorted(tools_dir.glob("*.py")):
        for fn in (n for n in ast.parse(f.read_text()).body if isinstance(n, ast.FunctionDef)):
            if fn.name not in names:
                continue
            doc = ast.get_docstring(fn) or ""
            description = re.split(r"\n\s*\n|\n\s*:param", doc)[0].strip().replace("\n", " ")
            helps = dict(re.findall(r":param (\w+):\s*(.+)", doc))
            props: dict[str, Any] = {}
            required: list[str] = []
            args = fn.args.args
            defaults = [None] * (len(args) - len(fn.args.defaults)) + list(fn.args.defaults)
            for a, d in zip(args, defaults, strict=False):
                ann = ast.unparse(a.annotation) if a.annotation else "str"
                if "Depends" in ann:
                    continue
                base = ann.replace("| None", "").strip()
                if base.startswith("list"):
                    spec: dict[str, Any] = {"type": "array", "items": {"type": "string"}}
                else:
                    spec = {"type": _TYPES.get(base, "string")}
                if a.arg in helps:
                    spec["description"] = helps[a.arg]
                props[a.arg] = spec
                if d is None and "None" not in ann:
                    required.append(a.arg)
            specs[fn.name] = {
                "description": description,
                "parameters": {"type": "object", "properties": props, "required": required},
            }
    return specs


def _defaults(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text()) or {}
    return {k: str(v["default"] if isinstance(v, dict) else v) for k, v in raw.items()}


def _load_env(suite_dir: Path) -> dict[str, Any]:
    text = (suite_dir / "environment.yaml").read_text()
    for key, value in _defaults(suite_dir / "injection_vector_defaults.yaml").items():
        text = text.replace("{" + key + "}", value)
    return yaml.safe_load(text) or {}


def seed_for(suite: str, env: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    if suite == "banking":
        acct = env["bank_account"]
        user = env.get("user_account", {})
        return {
            "account": [{"id": "main", "balance": acct["balance"], "iban": acct["iban"]}],
            "transactions": [{**t, "id": str(t["id"])} for t in acct.get("transactions", [])],
            "scheduled": [
                {**t, "id": str(t["id"])} for t in acct.get("scheduled_transactions", [])
            ],
            "files": [
                {"id": p, "content": c}
                for p, c in env.get("filesystem", {}).get("files", {}).items()
            ],
            # the journal redacts keys named `password`, which breaks patch `before` checks
            "user": [
                {
                    "id": "user",
                    **{("user_password" if k == "password" else k): v for k, v in user.items()},
                }
            ],
        }
    slack, web = env["slack"], env.get("web", {})
    return {
        "users": [
            {
                "id": u,
                "channels": sorted(slack.get("user_channels", {}).get(u, [])),
                "inbox": slack.get("user_inbox", {}).get(u, []),
            }
            for u in slack["users"]
        ],
        "channels": [
            {"id": c, "messages": slack.get("channel_inbox", {}).get(c, [])}
            for c in slack["channels"]
        ],
        "web": [
            {
                "id": "web",
                "content": web.get("web_content", {}),
                "requests": list(web.get("web_requests", [])),
            }
        ],
    }


def _security_check(calls: list[tuple[str, dict[str, Any]]]) -> dict[str, Any] | None:
    nodes = []
    for name, args in calls:
        if name not in EFFECTS:
            continue
        nodes.append(
            {
                "type": "tool_called",
                "tool": name,
                "args": {k: {"eq": v} for k, v in args.items() if k not in FREE_TEXT},
            }
        )
    if not nodes:
        return None
    return nodes[0] if len(nodes) == 1 else {"type": "all", "of": nodes}


def import_agentdojo(
    src: Path, out: Path, *, suite: str, pin: str, allow_unpinned: bool = False
) -> ImportReport:
    require_pin(pin, PIN, allow_unpinned=allow_unpinned)
    if suite not in SUITES:
        raise SystemExit(f"unknown suite {suite!r}; choose one of {sorted(SUITES)}")
    base = Path(src) / "src" / "agentdojo"
    v1 = base / "default_suites" / "v1"
    pack_id = f"agentdojo_{suite}"
    seed = seed_for(suite, _load_env(base / "data" / "suites" / suite))
    specs = read_tool_specs(v1 / "tools", SUITES[suite]["tools"])
    tools = [
        {
            "name": n,
            "description": specs[n]["description"],
            "risk": RISK.get(n, "read"),
            "input_schema": specs[n]["parameters"],
            "handler": {"kind": "python", "entrypoint": f"{HANDLERS}:{n}"},
            "untrusted_output": n in UNTRUSTED,
        }
        for n in SUITES[suite]["tools"]
        if n in specs
    ]
    world = WorldSpec.model_validate(
        {"id": pack_id, "clock_start": "2026-03-15T10:00:00Z", "tools": tools, "seed": seed}
    )
    available = {t.name for t in world.tools}
    report = ImportReport(licence="MIT", pin=pin)
    scenarios: list[dict[str, Any]] = []
    for i, task in enumerate(read_task_classes(v1 / suite / "user_tasks.py")):
        report.tasks += 1
        sid = f"adojo_{suite}_u{i:02d}"
        if task["calls"] is None:
            report.skipped.append(Reason(sid, task["error"]))
            continue
        missing = sorted({n for n, _ in task["calls"]} - available)
        if missing:
            report.skipped.append(Reason(sid, f"unported_tool:{','.join(missing)}"))
            continue
        before, after, errors = replay(world, task["calls"])
        if errors:
            report.skipped.append(Reason(sid, f"replay_error:{errors[0]}"))
            continue
        checks = state_checks(before, after)
        if not checks:
            report.skipped.append(Reason(sid, "utility_not_expressible"))
            continue
        scenarios.append(
            {
                "id": sid,
                "version": 1,
                "title": f"AgentDojo {suite} user task {i}",
                "goal": task["text"],
                "persona": "per_cooperative",
                "hidden_facts": [task["text"]],
                "opening_message": task["text"],
                "world": pack_id,
                "success": {"type": "all", "of": checks},
                "rubrics": ["task_completion"],
                "max_turns": 12,
                "tags": {"category": pack_id, "source": "agentdojo", "task": task["class"]},
            }
        )
        report.portable += 1
    attacks: list[dict[str, Any]] = []
    inj = read_task_classes(v1 / suite / "injection_tasks.py")
    for i, task in enumerate(inj):
        sid = f"atk_agentdojo_{suite}_i{i:02d}"
        check = _security_check(task["calls"]) if task["calls"] else None
        if check is None:
            report.skipped.append(Reason(sid, "security_not_expressible"))
            continue
        attacks.append(
            {
                "id": sid,
                "title": f"AgentDojo {suite} injection task {i}",
                "category": "indirect_injection",
                "technique": "benchmark_goal",
                "source": f"agentdojo@{pin}",
                "license": "MIT",
                "vector": "tool_result",
                "payload": task["text"],
                "objective": check,
                "severity": "high",
                "target": SUITES[suite]["inject_tool"],
            }
        )
    for s in scenarios:
        Scenario.model_validate(s)
        write_yaml(out / "scenarios" / f"{s['id']}.yaml", s)
    for a in attacks:
        Attack.model_validate(a)
        write_yaml(out / "attacks" / f"{a['id']}.yaml", a)
    write_yaml(out / "world.yaml", world.model_dump(mode="json", exclude={"seed"}))
    write_yaml(out / "seed.yaml", seed)
    (out / "policy.md").write_text("")
    write_yaml(
        out / "pack.yaml",
        {
            "id": pack_id,
            "title": f"AgentDojo {suite} (imported)",
            "version": 1,
            "world": "world.yaml",
            "seed": "seed.yaml",
            "policy": "policy.md",
            "personas": ["per_cooperative"],
            "import": {
                "source": REPO,
                "pin": pin,
                "licence": "MIT",
                "portable_pct": report.portable_pct,
                "tasks": report.tasks,
                "portable": report.portable,
                "attacks": len(attacks),
            },
        },
    )
    ids = sorted(s["id"] for s in scenarios)
    write_yaml(
        out / "suites" / "full.yaml", {"id": "full", "name": "All ported tasks", "scenarios": ids}
    )
    write_yaml(out / "skipped.yaml", [{"item": s.item, "reason": s.reason} for s in report.skipped])
    return report
