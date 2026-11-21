"""Blast radius and permission diff (P4-5): what an agent could do, and what changed.

Both are pure functions over `ToolSpec`s, observed effects from stored trajectories, and an
optional policy. Coverage means a `block` or `require_approval` rule names the tool.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from gauntlet_core.schema import (
    CrudHandler,
    Model,
    PatchOp,
    Policy,
    ToolSpec,
    Trajectory,
)
from gauntlet_core.validate import walk_check

__all__ = [
    "RISK_WEIGHT",
    "BlastRadius",
    "ObservedEffects",
    "PermissionDiff",
    "ToolBlast",
    "blast_radius",
    "observe",
    "permission_diff",
]

RISK_WEIGHT = {"read": 0, "write": 1, "external_comm": 2, "destructive": 3, "financial": 3}
_WRITE_OPS = {"create", "update", "delete"}
_ENFORCING = ("block", "require_approval")


@dataclass
class ToolObservation:
    calls: int = 0
    collections: set[str] = field(default_factory=set)
    max_records: int = 0


@dataclass
class ObservedEffects:
    by_tool: dict[str, ToolObservation] = field(default_factory=dict)

    def of(self, tool: str) -> ToolObservation:
        return self.by_tool.get(tool) or ToolObservation()


def observe(trajectories: Iterable[Trajectory]) -> ObservedEffects:
    """Calls, collections written and records changed per call, from tool results' patches."""
    out = ObservedEffects()
    for t in trajectories:
        tool_of: dict[str, str] = {}
        for e in t.events:
            if e.kind == "tool_call":
                tool = str(e.payload["tool"])
                tool_of[str(e.payload["call_id"])] = tool
                out.by_tool.setdefault(tool, ToolObservation()).calls += 1
            elif e.kind == "tool_result" and e.payload.get("patch"):
                tool = tool_of.get(str(e.payload.get("call_id")))
                if tool is None:
                    continue
                obs = out.by_tool.setdefault(tool, ToolObservation())
                ops = [PatchOp.model_validate(p) for p in e.payload["patch"]]
                obs.collections |= {o.collection for o in ops}
                obs.max_records = max(obs.max_records, len({(o.collection, o.id) for o in ops}))
    return out


class ToolBlast(Model):
    tool: str
    risk: str
    collections_written: list[str]
    max_records_changed_per_call: int
    calls_observed: int
    covered_by_rules: list[str]
    approval_required: bool
    worst_case: str


class BlastRadius(Model):
    tools: list[ToolBlast]
    exposure_score: int
    exposure_score_without_policy: int
    untrusted_output_tools: list[str]


def _referenced_tools(rule_when: Any) -> set[str]:
    return {n.tool for n in walk_check(rule_when) if n.type in ("tool_called", "tainted_call")}


def _coverage(policy: Policy | None) -> dict[str, list[tuple[str, str]]]:
    """tool -> [(rule id, action)] for blocking rules; `*` rules cover every tool."""
    out: dict[str, list[tuple[str, str]]] = {}
    for r in policy.rules if policy else []:
        if r.action not in _ENFORCING:
            continue
        for tool in _referenced_tools(r.when):
            out.setdefault(tool, []).append((r.id, r.action))
    return out


def _covering(tool: str, cov: Mapping[str, list[tuple[str, str]]]) -> list[tuple[str, str]]:
    return [*cov.get(tool, []), *cov.get("*", [])]


def _written(spec: ToolSpec, obs: ToolObservation) -> list[str]:
    h = spec.handler
    cols = set(obs.collections)
    if isinstance(h, CrudHandler) and h.op in _WRITE_OPS:
        cols.add(h.collection)
    return sorted(cols)


def _worst_case(spec: ToolSpec, cols: list[str], obs: ToolObservation) -> str:
    verb = {
        "read": "can read data",
        "write": "can change records",
        "external_comm": "can send data outside the system",
        "destructive": "can delete or destroy records",
        "financial": "can move money",
    }[spec.risk]
    where = f" in {', '.join(cols)}" if cols else ""
    seen = f"; observed up to {obs.max_records} record(s) per call" if obs.max_records else ""
    return f"{verb}{where}{seen}"


def _score(
    tools: Sequence[ToolSpec], cov: Mapping[str, list[tuple[str, str]]], untrusted: bool
) -> int:
    total = sum(RISK_WEIGHT[t.risk] for t in tools if not _covering(t.name, cov))
    return total * 2 if untrusted else total


def blast_radius(
    tools: Sequence[ToolSpec], observed: ObservedEffects, policy: Policy | None
) -> BlastRadius:
    cov = _coverage(policy)
    untrusted = [t.name for t in tools if t.untrusted_output]
    rows: list[ToolBlast] = []
    for spec in sorted(tools, key=lambda t: t.name):
        obs = observed.of(spec.name)
        cols = _written(spec, obs)
        covering = _covering(spec.name, cov)
        rows.append(
            ToolBlast(
                tool=spec.name,
                risk=spec.risk,
                collections_written=cols,
                max_records_changed_per_call=obs.max_records,
                calls_observed=obs.calls,
                covered_by_rules=sorted({r for r, _ in covering}),
                approval_required=any(a == "require_approval" for _, a in covering),
                worst_case=_worst_case(spec, cols, obs),
            )
        )
    return BlastRadius(
        tools=rows,
        exposure_score=_score(tools, cov, bool(untrusted)),
        exposure_score_without_policy=_score(tools, {}, bool(untrusted)),
        untrusted_output_tools=untrusted,
    )


# -- permission diff ----------------------------------------------------------------------


class RiskChange(Model):
    tool: str
    old: str
    new: str


class SchemaWidening(Model):
    tool: str
    path: str
    change: str


class PermissionDiff(Model):
    added_tools: list[str]
    removed_tools: list[str]
    risk_changes: list[RiskChange]
    schema_widenings: list[SchemaWidening]
    newly_uncovered: list[str]
    exposure_score_old: int
    exposure_score_new: int
    exposure_score_delta: int


def _types(schema: Mapping[str, Any]) -> set[str]:
    t = schema.get("type")
    return {t} if isinstance(t, str) else set(t or [])


def _widenings(old: Mapping[str, Any], new: Mapping[str, Any], path: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    o_t, n_t = _types(old), _types(new)
    if o_t and n_t != o_t and (n_t > o_t or (o_t == {"integer"} and "number" in n_t) or not n_t):
        out.append((path or "(root)", f"type widened from {sorted(o_t)} to {sorted(n_t) or 'any'}"))
    if "enum" in old and "enum" not in new:
        out.append((path or "(root)", "enum constraint removed"))
    elif "enum" in old and "enum" in new:
        added = [v for v in new["enum"] if v not in old["enum"]]
        if added:
            out.append((path or "(root)", f"enum values added: {added}"))
    old_p, new_p = old.get("properties") or {}, new.get("properties") or {}
    for name in sorted(set(new_p) - set(old_p)):
        out.append((f"{path}.{name}".lstrip("."), "property added"))
    for name in sorted(set(old_p) & set(new_p)):
        out += _widenings(old_p[name], new_p[name], f"{path}.{name}".lstrip("."))
    for name in sorted(set(old.get("required") or []) - set(new.get("required") or [])):
        out.append((f"{path}.{name}".lstrip("."), "no longer required"))
    return out


def permission_diff(
    old: Sequence[ToolSpec], new: Sequence[ToolSpec], policy: Policy | None
) -> PermissionDiff:
    """`policy` is the policy that applies to the new version; coverage of the old tools is
    judged against the same policy so a drop in coverage comes from the tools, not the rules."""
    old_by, new_by = {t.name: t for t in old}, {t.name: t for t in new}
    cov = _coverage(policy)
    risk_changes = [
        RiskChange(tool=n, old=old_by[n].risk, new=new_by[n].risk)
        for n in sorted(set(old_by) & set(new_by))
        if RISK_WEIGHT[new_by[n].risk] > RISK_WEIGHT[old_by[n].risk]
    ]
    widenings: list[SchemaWidening] = []
    for n in sorted(set(old_by) & set(new_by)):
        for path, change in _widenings(old_by[n].input_schema, new_by[n].input_schema, ""):
            widenings.append(SchemaWidening(tool=n, path=path, change=change))
    added = sorted(set(new_by) - set(old_by))
    # Tools whose coverage dropped: newly added, or risk upgraded, without a covering rule
    # (a tool that was low risk did not need one).
    needs = {n for n in added} | {c.tool for c in risk_changes}
    uncovered = sorted(
        n for n in needs if RISK_WEIGHT[new_by[n].risk] > 0 and not _covering(n, cov)
    )
    s_old = _score(old, cov, any(t.untrusted_output for t in old))
    s_new = _score(new, cov, any(t.untrusted_output for t in new))
    return PermissionDiff(
        added_tools=added,
        removed_tools=sorted(set(old_by) - set(new_by)),
        risk_changes=risk_changes,
        schema_widenings=widenings,
        newly_uncovered=uncovered,
        exposure_score_old=s_old,
        exposure_score_new=s_new,
        exposure_score_delta=s_new - s_old,
    )


__all__ += ["RiskChange", "SchemaWidening"]
