"""The judge cascade (03-hard-cores 5.3): rule -> small -> strong.

With a `ctx`, every model call is a journaled `llm` effect (`llm_effect`), so a replayed
episode re-derives identical verdicts with zero model calls. Without one (rejudge,
calibration) the gateway is called directly.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from gauntlet_core.engine import EpisodeCtx, PermanentEffectError
from gauntlet_core.llm import (
    GatewayError,
    LLMResult,
    lenient_json,
    structured_call,
    structured_effect,
)
from gauntlet_core.llm.gateway import Gateway
from gauntlet_core.schema import SEVERITY_ORDER, Cost, Json, Rubric, Trajectory, Verdict

from .cache import CachingGateway, JudgeCache
from .evidence import JudgeOutput, to_evidence, validate_evidence
from .render import build_messages, event_texts

RuleStage = Callable[[Trajectory], Verdict | None]
ContextProvider = Callable[[str, Trajectory], str]  # (rubric id, trajectory) -> extra context
SMALL_ROLE = "judge_small"
STRONG_ROLE = "judge_strong"
NOT_CALIBRATED = "[not calibrated: cannot fail a CI gate] "


@dataclass
class StageResult:
    """Outcome of one judge stage (including its single evidence retry)."""

    output: JudgeOutput | None = None
    errors: list[str] = field(default_factory=list)
    cost: Cost = field(default_factory=Cost)
    model: str | None = None

    @property
    def valid(self) -> bool:
        return self.output is not None and not self.errors


async def _call(
    ctx: EpisodeCtx | None, gateway: Gateway, role: str, messages: list[Json]
) -> LLMResult:
    """One judge call with the shared recovery: repair retry, then JSON-from-prose. There is
    deliberately no plain-text fallback: a verdict is never invented from free text."""
    lenient = lenient_json(JudgeOutput)
    if ctx is not None:
        return await structured_effect(
            ctx, gateway, role, messages, response_model=JudgeOutput, lenient=lenient,
            temperature=0.0,
        )  # fmt: skip

    async def call(msgs: list[Json], max_output_scale: int = 1) -> LLMResult:
        return await gateway.complete(
            role,
            msgs,
            response_model=JudgeOutput,
            temperature=0.0,
            max_output_scale=max_output_scale,
        )

    return await structured_call(call, messages, lenient=lenient)


async def run_stage(
    gateway: Gateway,
    role: str,
    rubric: Rubric,
    traj: Trajectory,
    *,
    ctx: EpisodeCtx | None = None,
    policy_text: str = "",
    context_text: str = "",
) -> StageResult:
    """One judge call, validated; one retry with the validation error appended."""
    messages = build_messages(rubric, traj, policy_text=policy_text, context_text=context_text)
    texts = event_texts(traj)
    na_allowed = rubric.na_definition is not None
    res = StageResult()
    for attempt in (0, 1):
        try:
            r = await _call(ctx, gateway, role, messages)
        except (GatewayError, PermanentEffectError) as e:
            res.errors = [f"judge call failed: {e}"]
            res.output = None
            return res
        res.cost = res.cost + r.cost
        res.model = r.model or res.model
        out = r.parsed
        if not isinstance(out, JudgeOutput):
            res.output, res.errors = None, ["judge returned no structured output"]
            return res
        res.output = out
        res.errors = validate_evidence(out, texts, na_allowed=na_allowed)
        if not res.errors:
            return res
        if attempt == 0:
            messages = [
                *messages,
                {"role": "assistant", "content": out.model_dump_json()},
                {
                    "role": "user",
                    "content": "Your evidence was invalid: "
                    + "; ".join(res.errors)
                    + ". Return the full JSON again with corrected evidence quotes copied "
                    "verbatim from the transcript.",
                },
            ]
    return res


def accept_small(severity: str, small: StageResult, tau: float) -> bool:
    """Small verdict is final iff evidence valid, confidence >= tau, and it is not a
    high or critical severity failure (those are always confirmed by the strong judge)."""
    if not small.valid or small.output is None:
        return False
    out = small.output
    if out.confidence < tau:
        return False
    return not (SEVERITY_ORDER[severity] >= SEVERITY_ORDER["high"] and out.result == "fail")


def _verdict(
    rubric: Rubric,
    stage: str,
    res: StageResult,
    *,
    evaluator: str,
    error: str | None = None,
) -> Verdict:
    out = res.output
    base: dict[str, object] = {
        "evaluator": evaluator,
        "rubric_version": rubric.version,
        "criterion": rubric.id,
        "severity": rubric.severity,
        "hard_fail": rubric.hard_fail,
        "stage": stage,
        "model": res.model,
        "cost": res.cost,
    }
    if error is not None or out is None:
        return Verdict(
            **base,  # type: ignore[arg-type]
            result="error",
            confidence=0.0,
            reasoning=error or "; ".join(res.errors) or "judge failed",
        )
    return Verdict(
        **base,  # type: ignore[arg-type]
        result=out.result,
        confidence=out.confidence,
        evidence=to_evidence(out),
        reasoning=out.reasoning,
    )


def apply_gating(rubric: Rubric, v: Verdict) -> Verdict:
    """Ungated rubrics still report but cannot fail a CI gate (hard_fail is cleared)."""
    if rubric.gating_allowed or v.stage == "rule":
        return v
    return v.model_copy(update={"hard_fail": False, "reasoning": NOT_CALIBRATED + v.reasoning})


async def evaluate_rubric(
    rubric: Rubric,
    traj: Trajectory,
    gateway: Gateway,
    *,
    ctx: EpisodeCtx | None = None,
    policy_text: str = "",
    context_text: str = "",
    rule_stage: RuleStage | None = None,
    small_role: str = SMALL_ROLE,
    strong_role: str = STRONG_ROLE,
    escalate: bool = True,
    evaluator: str | None = None,
) -> Verdict:
    """Run the cascade for one rubric. `escalate=False` is the small-judge-only mode used by
    the simulator-fidelity rubric: a valid small verdict is final, an invalid one is `error`."""
    ev = evaluator or f"judge:{rubric.id}"
    if rule_stage is not None:
        decided = rule_stage(traj)
        if decided is not None:
            return decided
    kw = {"ctx": ctx, "policy_text": policy_text, "context_text": context_text}
    small = await run_stage(gateway, small_role, rubric, traj, **kw)  # type: ignore[arg-type]
    if not escalate:
        return apply_gating(rubric, _verdict(rubric, "small", small, evaluator=ev))
    if accept_small(rubric.severity, small, rubric.threshold):
        return apply_gating(rubric, _verdict(rubric, "small", small, evaluator=ev))
    strong = await run_stage(gateway, strong_role, rubric, traj, **kw)  # type: ignore[arg-type]
    strong.cost = strong.cost + small.cost
    if strong.valid:
        return apply_gating(rubric, _verdict(rubric, "strong", strong, evaluator=ev))
    msg = "strong judge could not produce a valid verdict: " + (
        "; ".join(strong.errors) or "unknown"
    )
    return _verdict(rubric, "strong", strong, evaluator=ev, error=msg)


class JudgeEvaluator:
    """`Evaluator` (contracts section 5) over a list of rubrics. Bind the episode `ctx` so
    judge calls are journaled effects; sequential order keeps effect ordinals deterministic."""

    def __init__(
        self,
        rubrics: Sequence[Rubric],
        *,
        ctx: EpisodeCtx | None = None,
        policy_text: str = "",
        rule_stages: Mapping[str, RuleStage] | None = None,
        context_provider: ContextProvider | None = None,
        cache: JudgeCache | None = None,
        id: str = "judges",
    ) -> None:
        self.id = id
        self.rubrics = list(rubrics)
        self.ctx = ctx
        self.policy_text = policy_text
        self.rule_stages = dict(rule_stages or {})
        self.context_provider = context_provider
        self.cache = cache

    async def evaluate(self, traj: Trajectory, gateway: Gateway) -> list[Verdict]:
        gw: Gateway = CachingGateway(gateway, self.cache) if self.cache is not None else gateway
        return [
            await evaluate_rubric(
                r,
                traj,
                gw,
                ctx=self.ctx,
                policy_text=self.policy_text,
                context_text=self.context_provider(r.id, traj) if self.context_provider else "",
                rule_stage=self.rule_stages.get(r.id),
            )
            for r in self.rubrics
        ]


def model_family(model_id: str) -> str:
    """Vendor-ish family of a litellm model id: 'openrouter/qwen/qwen3.7-flash' -> 'qwen'."""
    last = model_id.lower().rsplit("/", 1)[-1]
    m = re.match(r"[a-z]+", last)
    return m.group() if m else last


def self_preference_warning(judge_models: Sequence[str], target_model: str | None) -> str | None:
    """Caution text when a judge shares a family with the hosted target, else None."""
    if not target_model:
        return None
    fam = model_family(target_model)
    shared = sorted({m for m in judge_models if model_family(m) == fam})
    if not shared:
        return None
    return (
        f"Judge model(s) {', '.join(shared)} share a model family ({fam}) with the target "
        f"{target_model}; judges tend to favour their own family's output. "
        "Treat scores with caution."
    )
