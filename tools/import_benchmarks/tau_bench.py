"""tau-bench retail importer (MIT, Sierra). Reads a checkout of the upstream repository:

    <src>/tau_bench/envs/retail/data/{users,orders,products}.json
    <src>/tau_bench/envs/retail/tools/*.py      (tool names, descriptions, parameter schemas)
    <src>/tau_bench/envs/retail/tasks_test.py   (Task(...) literals)
    <src>/tau_bench/envs/retail/wiki.md         (the policy, copied verbatim)

Tool semantics are our reviewed pure ports (`tau_handlers.py`); tool names, descriptions and
parameter schemas are read from upstream. A task becomes a scenario whose `success` is derived by
replaying its ground-truth actions through our handlers on the initial data: one `state` check per
changed record field, plus one output check per required output string. Tasks that use a tool we
have not ported, whose replay fails, or that have nothing checkable are skipped with a reason.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

from gauntlet_core.schema import Scenario, WorldSpec

from .common import ImportReport, Reason, replay, require_pin, state_checks, write_yaml

__all__ = ["PIN", "REPO", "import_tau_bench"]

PIN = "59a200c6d575d595120f1cb70fea53cef0632f6b"
REPO = "https://github.com/sierra-research/tau-bench"
HANDLERS = "tools.import_benchmarks.tau_handlers"
PORTED = (
    "find_user_id_by_email",
    "find_user_id_by_name_zip",
    "get_user_details",
    "get_order_details",
    "get_product_details",
    "list_all_product_types",
    "cancel_pending_order",
    "modify_pending_order_address",
    "modify_user_address",
    "return_delivered_order_items",
    "transfer_to_human_agents",
)
RISK = {
    "cancel_pending_order": "write",
    "modify_pending_order_address": "write",
    "modify_user_address": "write",
    "return_delivered_order_items": "write",
    "transfer_to_human_agents": "write",
}
NO_STATE = {"think", "calculate"}  # upstream pseudo-tools that never change the database


def _call_args(node: ast.Call) -> dict[str, Any]:
    return {k.arg: ast.literal_eval(k.value) for k in node.keywords if k.arg}


def read_tasks(path: Path) -> list[dict[str, Any]]:
    """The `Task(...)` literals of a tasks file, in order."""
    tasks = []
    calls = [n for n in ast.walk(ast.parse(path.read_text())) if isinstance(n, ast.Call)]
    for node in sorted(calls, key=lambda n: (n.lineno, n.col_offset)):
        if getattr(node.func, "id", "") == "Task":
            fields: dict[str, Any] = {}
            for kw in node.keywords:
                if kw.arg == "actions":
                    fields["actions"] = [
                        _call_args(c)
                        for c in getattr(kw.value, "elts", [])
                        if isinstance(c, ast.Call)
                    ]
                elif kw.arg:
                    fields[kw.arg] = ast.literal_eval(kw.value)
            tasks.append(fields)
    return tasks


def read_tool_infos(tools_dir: Path) -> dict[str, dict[str, Any]]:
    """`name -> {description, parameters}` from each tool's `get_info` literal."""
    infos: dict[str, dict[str, Any]] = {}
    for f in sorted(tools_dir.glob("*.py")):
        for fn in ast.walk(ast.parse(f.read_text())):
            if isinstance(fn, ast.FunctionDef) and fn.name == "get_info":
                for ret in (
                    n for n in ast.walk(fn) if isinstance(n, ast.Return) and n.value is not None
                ):
                    try:
                        info = ast.literal_eval(ret.value)["function"]  # type: ignore[arg-type]
                    except (ValueError, KeyError, TypeError):
                        continue
                    infos[info["name"]] = info
    return infos


def number_tolerant(text: str) -> str:
    """Regex for `text`, case-insensitive, allowing thousands commas inside numbers (the
    upstream comparison removes commas from the agent's reply)."""
    out = []
    for i, ch in enumerate(text.lower()):
        out.append(re.escape(ch))
        if ch.isdigit() and i + 1 < len(text) and text[i + 1].isdigit():
            out.append(",?")
    return "(?i)" + "".join(out)


def _seed(data_dir: Path) -> dict[str, list[dict[str, Any]]]:
    def load(name: str) -> list[dict[str, Any]]:
        raw = json.loads((data_dir / f"{name}.json").read_text())
        return [{**v, "id": k} for k, v in raw.items()]

    return {"users": load("users"), "orders": load("orders"), "products": load("products")}


def _world(infos: dict[str, dict[str, Any]], seed: dict[str, Any]) -> WorldSpec:
    tools = []
    for name in PORTED:
        if name not in infos:
            continue
        tools.append(
            {
                "name": name,
                "description": infos[name]["description"],
                "risk": RISK.get(name, "read"),
                "input_schema": infos[name]["parameters"],
                "handler": {"kind": "python", "entrypoint": f"{HANDLERS}:{name}"},
            }
        )
    return WorldSpec.model_validate(
        {
            "id": "taubench_retail",
            "clock_start": "2026-03-15T10:00:00Z",
            "tools": tools,
            "seed": seed,
        }
    )


def import_tau_bench(
    src: Path, out: Path, *, pin: str, allow_unpinned: bool = False, limit: int | None = None
) -> ImportReport:
    require_pin(pin, PIN, allow_unpinned=allow_unpinned)
    root = Path(src) / "tau_bench" / "envs" / "retail"
    seed = _seed(root / "data")
    infos = read_tool_infos(root / "tools")
    world = _world(infos, seed)
    available = {t.name for t in world.tools}
    report = ImportReport(licence="MIT", pin=pin)
    scenarios: list[dict[str, Any]] = []
    for index, task in enumerate(read_tasks(root / "tasks_test.py")[: limit or None]):
        report.tasks += 1
        sid = f"tau_retail_{index:03d}"
        actions = [a for a in task.get("actions", []) if a["name"] not in NO_STATE]
        missing = sorted({a["name"] for a in actions} - available)
        if missing:
            report.skipped.append(Reason(sid, f"unported_tool:{','.join(missing)}"))
            continue
        before, after, errors = replay(world, [(a["name"], a.get("kwargs", {})) for a in actions])
        if errors:
            report.skipped.append(Reason(sid, f"replay_error:{errors[0]}"))
            continue
        checks: list[dict[str, Any]] = state_checks(before, after)
        checks += [
            {"type": "output", "matcher": {"regex": number_tolerant(str(o))}, "scope": "any"}
            for o in task.get("outputs", [])
        ]
        if not checks:
            report.skipped.append(Reason(sid, "no_checkable_outcome"))
            continue
        scenarios.append(
            {
                "id": sid,
                "version": 1,
                "title": f"tau-bench retail task {index}",
                "goal": task["instruction"],
                "persona": "per_cooperative",
                "hidden_facts": [task["instruction"]],
                "world": "taubench_retail",
                "success": {"type": "all", "of": checks},
                "rubrics": ["task_completion"],
                "max_turns": 30,
                "tags": {
                    "category": "taubench_retail",
                    "source": "tau-bench",
                    "user_id": str(task.get("user_id", "")),
                },
            }
        )
        report.portable += 1
    for s in scenarios:  # fail loudly on anything that is not a valid scenario
        Scenario.model_validate(s)
        write_yaml(out / "scenarios" / f"{s['id']}.yaml", s)
    write_yaml(out / "world.yaml", {**world.model_dump(mode="json", exclude={"seed"})})
    write_yaml(out / "seed.yaml", seed)
    wiki = root / "wiki.md"
    (out / "policy.md").write_text(wiki.read_text() if wiki.is_file() else "")
    write_yaml(
        out / "pack.yaml",
        {
            "id": "taubench_retail",
            "title": "tau-bench retail (imported)",
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
            },
        },
    )
    ids = sorted(s["id"] for s in scenarios)
    write_yaml(
        out / "suites" / "full.yaml", {"id": "full", "name": "All ported tasks", "scenarios": ids}
    )
    write_yaml(
        out / "suites" / "smoke.yaml",
        {"id": "smoke", "name": "Smoke (first 5)", "scenarios": ids[:5]},
    )
    write_yaml(out / "skipped.yaml", [{"item": s.item, "reason": s.reason} for s in report.skipped])
    return report
