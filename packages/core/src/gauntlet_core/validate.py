"""Static validation of scenarios, worlds and packs (CQ-B12). Pure, no I/O except importing
handler modules. Used by the runner (step 1), `gauntlet validate` and pack loading."""

from __future__ import annotations

from collections.abc import Collection, Iterator, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from gauntlet_core.checks import names as detector_names
from gauntlet_core.schema import (
    PythonHandler,
    Scenario,
    ToolSpec,
    WorldSpec,
)
from gauntlet_core.world import WorldState, WorldView, assert_pure, resolve_handler

if TYPE_CHECKING:
    from gauntlet_core.packs import Pack

__all__ = [
    "Issue",
    "contains_judge",
    "validate_pack",
    "validate_scenario",
    "validate_world",
    "walk_check",
]


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    path: str = ""

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def line(self) -> str:
        return f"{self.path}:{self.code}:{self.message}"


def walk_check(check: Any) -> Iterator[Any]:
    """The node and every descendant."""
    yield check
    kind = check.type
    if kind in ("all", "any"):
        for c in check.of:
            yield from walk_check(c)
    elif kind == "not":
        yield from walk_check(check.check)
    elif kind == "sequence":
        yield from walk_check(check.first)
        yield from walk_check(check.then)


def contains_judge(check: Any) -> bool:
    return any(n.type == "judge" for n in walk_check(check))


def _check_issues(check: Any, tools: Collection[str], where: str) -> list[Issue]:
    out: list[Issue] = []
    known = set(detector_names())
    for n in walk_check(check):
        if n.type == "judge":
            out.append(Issue("judge_check_unsupported", f"{where}: judge nodes are not allowed"))
        elif (n.type == "tool_called" and n.tool != "*" and n.tool not in tools) or (
            n.type == "tainted_call" and n.tool != "*" and n.tool not in tools
        ):
            out.append(Issue("unknown_tool", f"{where}: tool {n.tool!r} is not in the world"))
        elif n.type == "detector" and n.name not in known:
            out.append(Issue("unknown_detector", f"{where}: detector {n.name!r} is not registered"))
    return out


def _matchers(node: Any) -> Iterator[Any]:
    kind = node.type
    if kind == "tool_called":
        yield from node.args.values()
    elif kind == "state":
        yield node.matcher
        yield from (node.where or {}).values()
    elif kind == "output":
        yield node.matcher
    elif kind == "state_diff":
        yield from (node.changed or {}).values()


def _seed_issues(check: Any, world: WorldSpec, where: str, extra: Any = None) -> list[Issue]:
    """`state` and `{ref: world:...}` nodes must name collections (and records) in the seed."""
    out: list[Issue] = []
    for n in walk_check(check):
        if n.type == "state":
            recs = world.seed.get(n.collection)
            if recs is not None or n.collection in (extra or {}):
                recs = [*(recs or []), *(extra or {}).get(n.collection, [])]
            if recs is None:
                out.append(Issue("unknown_collection", f"{where}: no collection {n.collection!r}"))
            elif n.id is not None and n.id not in {str(r.get("id")) for r in recs}:
                out.append(
                    Issue("unknown_record", f"{where}: {n.collection}/{n.id} is not in the seed")
                )
        for m in _matchers(n):
            ref = m.ref or ""
            if ref.startswith("world:"):
                coll = ref[len("world:") :].partition("/")[0]
                if coll not in world.seed and coll not in (extra or {}):
                    out.append(
                        Issue(
                            "unknown_ref_collection", f"{where}: ref to unknown collection {coll!r}"
                        )
                    )
    return out


def validate_scenario(
    scenario: Scenario,
    world: WorldSpec,
    *,
    persona_ids: Collection[str] | None = None,
    rubric_ids: Collection[str] | None = None,
    strict: bool = False,
) -> list[Issue]:
    """`strict` adds the authoring-quality rules used for generated scenarios: non-empty
    hidden facts and `max_turns` in 1..100."""
    issues: list[Issue] = []
    if strict:
        if not scenario.hidden_facts:
            issues.append(Issue("empty_hidden_facts", "hidden_facts must not be empty"))
        if not 1 <= scenario.max_turns <= 100:
            issues.append(Issue("bad_max_turns", f"max_turns {scenario.max_turns} not in 1..100"))
    if isinstance(scenario.world, WorldSpec):
        world = scenario.world
        if scenario.attack is not None and scenario.tags.get("placed") != "true":
            issues.append(
                Issue(
                    "attack_inline_world",
                    "a scenario with an attack and an inline world must be placed by the "
                    "campaign builder (tags.placed = 'true')",
                )
            )
    tools = {t.name for t in world.tools}
    if isinstance(scenario.world, str) and world.id is not None and scenario.world != world.id:
        issues.append(
            Issue("unknown_world", f"scenario uses world {scenario.world!r}, pack has {world.id!r}")
        )
    if persona_ids is not None and scenario.persona not in persona_ids:
        issues.append(Issue("unknown_persona", f"persona {scenario.persona!r} not found"))
    if rubric_ids is not None:
        for r in scenario.rubrics:
            if r not in rubric_ids:
                issues.append(Issue("unknown_rubric", f"rubric {r!r} not found"))
    issues += _check_issues(scenario.success, tools, "success")
    extra = scenario.world_overrides
    issues += _seed_issues(scenario.success, world, "success", extra)
    for nc in scenario.forbidden:
        issues += _check_issues(nc.check, tools, f"forbidden.{nc.id}")
        issues += _seed_issues(nc.check, world, f"forbidden.{nc.id}", extra)
    return issues


_SAMPLE: dict[str, Any] = {
    "string": "x",
    "integer": 1,
    "number": 1,
    "boolean": True,
    "object": {},
    "array": [],
}


def _sample_args(spec: ToolSpec, seed: Mapping[str, list[dict[str, Any]]]) -> dict[str, Any]:
    props = spec.input_schema.get("properties", {})
    ids = {c: str(r[0]["id"]) for c, r in seed.items() if r}
    fallback = next(iter(ids.values()), "x")
    args: dict[str, Any] = {}
    for name in spec.input_schema.get("required", []):
        sub = props.get(name, {})
        if "enum" in sub:
            args[name] = sub["enum"][0]
        elif sub.get("type") == "string" and name.endswith("_id"):
            stem = name[: -len("_id")]
            args[name] = ids.get(stem + "s", ids.get(stem, fallback))
        else:
            args[name] = _SAMPLE.get(sub.get("type", "string"), "x")
    return args


def validate_world(world: WorldSpec, *, check_purity: bool = True) -> list[Issue]:
    issues: list[Issue] = []
    names = [t.name for t in world.tools]
    for dup in sorted({n for n in names if names.count(n) > 1}):
        issues.append(Issue("duplicate_tool", f"tool {dup!r} is defined more than once"))
    try:
        state = WorldState.from_seed(world.seed)
    except ValueError as e:
        return [*issues, Issue("bad_seed", str(e))]
    for t in world.tools:
        if isinstance(t.handler, PythonHandler):
            try:
                handler = resolve_handler(t)
            except (ImportError, AttributeError, ValueError) as e:
                issues.append(Issue("handler_import", f"{t.name}: {e}"))
                continue
            if check_purity:
                try:
                    assert_pure(
                        handler,
                        WorldView(state),
                        _sample_args(t, world.seed),
                        world.clock_start,
                    )
                except AssertionError as e:
                    issues.append(Issue("handler_impure", f"{t.name}: {e}"))
                except Exception:
                    pass
    return issues


def validate_pack(pack: Pack, *, check_purity: bool = True) -> list[Issue]:
    from gauntlet_core.eval.rubrics import load_rubrics

    rubric_ids = set(load_rubrics())
    issues = [
        Issue(i.code, i.message, "world.yaml")
        for i in validate_world(pack.world, check_purity=check_purity)
    ]
    for sid, scn in pack.scenarios.items():
        for i in validate_scenario(
            scn, pack.world, persona_ids=set(pack.personas), rubric_ids=rubric_ids
        ):
            issues.append(Issue(i.code, i.message, f"scenarios/{sid}.yaml"))
    for suite in pack.suites.values():
        for sid in suite.scenarios:
            if sid not in pack.scenarios:
                issues.append(
                    Issue(
                        "unknown_scenario",
                        f"suite {suite.id!r} lists {sid!r}",
                        f"suites/{suite.id}.yaml",
                    )
                )
    return issues
