"""The check language AST (contracts section 4). Evaluation lives in gauntlet_core.checks."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from .common import Evidence, Json, Model


class Matcher(Model):
    """A value test. Every key that is set must hold. `ref` resolves a comparison value."""

    eq: Any = None
    ne: Any = None
    in_: list[Any] | None = Field(default=None, alias="in")
    regex: str | None = None
    contains: Any = None
    gt: float | None = None
    gte: float | None = None
    lt: float | None = None
    lte: float | None = None
    exists: bool | None = None
    # "args:<path>", "result:<tool>.<path>", "world:<collection>/<id-or-{args.x}>/<path>"
    ref: str | None = None
    ref_op: Literal["eq", "ne", "gt", "gte", "lt", "lte"] = "eq"

    @model_validator(mode="after")
    def _non_empty(self) -> Matcher:
        if not (self.model_fields_set - {"ref_op"}):
            raise ValueError("matcher needs at least one operator")
        return self


class IntRange(Model):
    min: int | None = None
    max: int | None = None

    def contains(self, n: int) -> bool:
        return (self.min is None or n >= self.min) and (self.max is None or n <= self.max)


class All(Model):
    type: Literal["all"] = "all"
    of: list[Check]


class Any_(Model):
    type: Literal["any"] = "any"
    of: list[Check]


class Not(Model):
    type: Literal["not"] = "not"
    check: Check


class ToolCalled(Model):
    type: Literal["tool_called"] = "tool_called"
    tool: str  # exact name or "*"
    args: dict[str, Matcher] = {}
    count: IntRange = IntRange(min=1)
    ok: bool | None = None  # None = regardless of success


class Sequence(Model):
    type: Literal["sequence"] = "sequence"
    first: Check
    then: Check
    strict: bool = False


class State(Model):
    type: Literal["state"] = "state"
    collection: str
    id: str | None = None
    where: dict[str, Matcher] | None = None
    path: str
    matcher: Matcher

    @model_validator(mode="after")
    def _one_selector(self) -> State:
        if (self.id is None) == (self.where is None):
            raise ValueError("state check needs exactly one of `id` or `where`")
        return self


class StateDiffCheck(Model):
    type: Literal["state_diff"] = "state_diff"
    collection: str
    added: IntRange | None = None
    removed: IntRange | None = None
    changed: dict[str, Matcher] | None = None  # path -> matcher on the new value
    only: bool = False


class Output(Model):
    type: Literal["output"] = "output"
    actor: Literal["agent"] = "agent"
    matcher: Matcher
    scope: Literal["any", "last", "all"] = "any"


class CanaryLeaked(Model):
    type: Literal["canary_leaked"] = "canary_leaked"
    canary: str = "*"
    channels: list[Literal["output", "tool_args"]] = ["output", "tool_args"]


class Egress(Model):
    type: Literal["egress"] = "egress"
    allow_domains: list[str] = []
    allow_recipients: list[str] = []


class TaintedCall(Model):
    type: Literal["tainted_call"] = "tainted_call"
    tool: str = "*"
    risk: list[str] | None = None


class Detector(Model):
    type: Literal["detector"] = "detector"
    name: str
    params: Json = {}


class Judge(Model):
    type: Literal["judge"] = "judge"
    rubric: str


Check = Annotated[
    All
    | Any_
    | Not
    | ToolCalled
    | Sequence
    | State
    | StateDiffCheck
    | Output
    | CanaryLeaked
    | Egress
    | TaintedCall
    | Detector
    | Judge,
    Field(discriminator="type"),
]

for _m in (All, Any_, Not, Sequence):
    _m.model_rebuild()


class CheckResult(Model):
    holds: bool
    evidence: list[Evidence] = []
    needs_judge: list[str] = []


Decision = Literal["violates", "ok", "undetermined"]
