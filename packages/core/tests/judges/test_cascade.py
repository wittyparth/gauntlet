from gauntlet_core.engine import EpisodeCtx, MemoryJournalStore
from gauntlet_core.judges import (
    JudgeEvaluator,
    MemoryJudgeCache,
    evaluate_rubric,
    model_family,
    self_preference_warning,
)
from gauntlet_core.llm import AuthError, FakeLLM, FakeReply
from gauntlet_core.schema import Verdict
from judge_helpers import QUOTE, fail_reply, reply, rubric, traj

S, T = "judge_small", "judge_strong"


def llm(small=(), strong=()):
    return FakeLLM(by_role={S: list(small), T: list(strong)})


def roles(f):
    return [c.role for c in f.calls]


async def run(f, **kw):
    r = kw.pop("rubric", rubric())
    return await evaluate_rubric(r, traj(), f, **kw)


async def test_rule_stage_decides_without_model_calls():
    f = llm()
    decided = Verdict(evaluator="rule", criterion="no_unauthorised_refund", result="fail")
    v = await run(f, rule_stage=lambda t: decided)
    assert v is decided and f.calls == []


async def test_rule_stage_none_falls_through_to_small():
    f = llm([reply("pass", 0.95)])
    v = await run(f, rule_stage=lambda t: None)
    assert v.stage == "small" and roles(f) == [S]


async def test_small_accepted_when_confident():
    f = llm([reply("pass", 0.9)])
    v = await run(f)
    assert (v.stage, v.result, v.criterion, v.rubric_version) == (
        "small",
        "pass",
        "no_unauthorised_refund",
        3,
    )
    assert roles(f) == [S]


async def test_low_severity_fail_is_accepted_from_small():
    f = llm([fail_reply(0.9)])
    v = await run(f, rubric=rubric(severity="low"))
    assert v.stage == "small" and v.result == "fail" and v.evidence[0].quote == QUOTE


async def test_low_confidence_escalates_and_strong_is_final():
    f = llm([reply("pass", 0.5, usd=7)], [reply("fail", 0.9, [(2, QUOTE)], usd=30)])
    v = await run(f)
    assert roles(f) == [S, T]
    assert (v.stage, v.result) == ("strong", "fail")
    assert v.cost is not None and v.cost.usd_micros == 37  # both stages counted
    assert v.small_result == "pass"  # the review queue's disagreement signal


async def test_small_result_is_not_set_when_small_decides():
    v = await run(llm([reply("pass", 0.95)]))
    assert v.stage == "small" and v.small_result is None


async def test_high_severity_fail_always_confirmed_by_strong():
    for sev in ("high", "critical"):
        f = llm([fail_reply(0.99)], [reply("pass", 0.9)])
        v = await run(f, rubric=rubric(severity=sev))
        assert roles(f) == [S, T] and v.stage == "strong" and v.result == "pass"


async def test_high_severity_pass_not_escalated():
    f = llm([reply("pass", 0.95)])
    v = await run(f, rubric=rubric(severity="critical"))
    assert v.stage == "small" and roles(f) == [S]


async def test_invalid_evidence_retried_then_accepted():
    bad = reply("fail", 0.95, [(2, "a quote that is not there")])
    f = llm([bad, fail_reply(0.95)])
    v = await run(f, rubric=rubric(severity="low"))
    assert roles(f) == [S, S] and v.stage == "small"
    retry_msgs = f.calls[1].messages
    assert retry_msgs[-1]["content"].startswith("Your evidence was invalid")


async def test_invalid_small_twice_escalates_then_strong_ok():
    bad = reply("fail", 0.95, [(2, "a quote that is not there")])
    f = llm([bad, bad], [reply("pass", 0.9)])
    v = await run(f, rubric=rubric(severity="low"))
    assert roles(f) == [S, S, T] and v.stage == "strong"


async def test_strong_invalid_yields_error_verdict():
    bad = reply("fail", 0.95, [(2, "a quote that is not there")])
    f = llm([bad, bad], [bad, bad])
    v = await run(f)
    assert v.result == "error" and v.stage == "strong" and "valid verdict" in v.reasoning
    assert v.confidence == 0.0


async def test_gateway_error_in_small_escalates():
    f = llm([FakeReply(error=AuthError("nope"))], [reply("pass", 0.9)])
    v = await run(f)
    assert roles(f) == [S, T] and v.stage == "strong"


async def test_na_rejected_when_rubric_has_no_na_definition():
    f = llm([reply("na", 0.95)] * 2, [reply("pass", 0.9)])
    v = await run(f)
    assert v.stage == "strong" and roles(f) == [S, S, T]


async def test_ungated_rubric_cannot_hard_fail_and_is_marked():
    r = rubric(hard_fail=True, severity="low")
    v = await run(llm([fail_reply(0.95)]), rubric=r)
    assert v.result == "fail" and v.hard_fail is False
    assert v.reasoning.startswith("[not calibrated")
    v2 = await run(llm([fail_reply(0.95)]), rubric=r.model_copy(update={"gating_allowed": True}))
    assert v2.hard_fail is True and "not calibrated" not in v2.reasoning


async def test_no_escalation_mode_for_small_only():
    f = llm([reply("pass", 0.1)])
    v = await run(f, escalate=False)
    assert v.stage == "small" and roles(f) == [S]


async def test_judge_calls_are_journaled_effects_and_replay_without_calls():
    store = MemoryJournalStore()
    f1 = llm([reply("pass", 0.5, usd=7)], [reply("fail", 0.9, [(2, QUOTE)], usd=30)])
    ctx1 = await EpisodeCtx.open(store, "ep", run_id="r", rng_seed=1)
    v1 = await evaluate_rubric(rubric(), traj(), f1, ctx=ctx1)
    assert ctx1.spent.usd_micros == 37 and ctx1.live_effects == 2
    f2 = llm()
    ctx2 = await EpisodeCtx.open(store, "ep", run_id="r", rng_seed=1)
    v2 = await evaluate_rubric(rubric(), traj(), f2, ctx=ctx2)
    assert f2.calls == [] and v2 == v1


async def test_cache_hit_avoids_a_call_even_inside_an_episode():
    cache = MemoryJudgeCache()
    ev = JudgeEvaluator([rubric()], cache=cache)
    f1 = llm([reply("pass", 0.95)])
    (a,) = await ev.evaluate(traj(), f1)
    f2 = llm()
    (b,) = await ev.evaluate(traj(), f2)
    assert f2.calls == [] and cache.hits == 1
    assert (b.result, b.stage) == (a.result, a.stage)
    # a different rubric version is a different key
    ev3 = JudgeEvaluator([rubric(version=4)], cache=cache)
    f3 = llm([reply("pass", 0.95)])
    await ev3.evaluate(traj(), f3)
    assert len(f3.calls) == 1
    # journaled path: cached model call, but the llm effect still exists in the journal
    store = MemoryJournalStore()
    ctx = await EpisodeCtx.open(store, "ep", run_id="r", rng_seed=1)
    ev4 = JudgeEvaluator([rubric()], ctx=ctx, cache=cache)
    await ev4.evaluate(traj(), llm())
    assert ctx.live_effects == 1


async def test_evaluator_runs_rubrics_in_order_with_rule_stages():
    decided = Verdict(evaluator="rule", criterion="b", result="pass")
    ev = JudgeEvaluator([rubric(id="a"), rubric(id="b")], rule_stages={"b": lambda t: decided})
    out = await ev.evaluate(traj(), llm([reply("pass", 0.95)]))
    assert [v.criterion for v in out] == ["a", "b"] and out[1] is decided


async def test_context_provider_text_reaches_the_judge_prompt_per_rubric():
    seen: list[tuple[str, str]] = []

    def provider(rubric_id, trajectory):
        seen.append((rubric_id, "x"))
        return "HINT for a" if rubric_id == "a" else ""

    ev = JudgeEvaluator([rubric(id="a"), rubric(id="b")], context_provider=provider)
    f = llm([reply("pass", 0.95), reply("pass", 0.95)])
    await ev.evaluate(traj(), f)
    prompts = ["\n".join(m["content"] for m in c.messages) for c in f.calls]
    assert "<extra_context>\nHINT for a" in prompts[0]
    assert "<extra_context>" not in prompts[1]
    assert [r for r, _ in seen] == ["a", "b"]


def test_self_preference_warning():
    assert model_family("openrouter/qwen/qwen3.7-flash") == "qwen"
    w = self_preference_warning(["openrouter/qwen/qwen3.7-flash"], "openrouter/qwen/qwen3-max")
    assert w and "qwen" in w
    assert (
        self_preference_warning(["openrouter/qwen/qwen3.7-flash"], "openrouter/z-ai/glm-5") is None
    )
    assert self_preference_warning(["x/y"], None) is None


GOOD_JSON = '{"reasoning": "ok", "evidence": [], "result": "pass", "confidence": 0.95}'


async def test_malformed_judge_output_gets_one_repair_retry_with_ctx():
    """Empty replies were the real failure in the first live run (llm effects 3, 4, 6)."""
    ctx = await EpisodeCtx.open(MemoryJournalStore(), "ep", run_id="r", rng_seed=1)
    f = llm([FakeReply(text=""), FakeReply(text=GOOD_JSON)])
    v = await run(f, ctx=ctx)
    assert v.stage == "small" and v.result == "pass" and roles(f) == [S, S]
    assert "could not be used" in f.calls[1].messages[-1]["content"]


async def test_judge_lenient_parse_extracts_fenced_json_but_never_plain_text():
    f = llm([FakeReply(text="x"), FakeReply(text=f"Here you go:\n```json\n{GOOD_JSON}\n```")])
    v = await run(f)  # no ctx: rejudge path shares the same recovery
    assert v.stage == "small" and v.result == "pass" and roles(f) == [S, S]
    f2 = llm([FakeReply(text="x"), FakeReply(text="I think this passes")], [FakeReply(text="")] * 2)
    v2 = await run(f2)
    assert v2.result == "error"  # no verdict is invented from prose


def test_cache_key_includes_reasoning():
    from gauntlet_core.judges import cache_key
    from pydantic import BaseModel

    class M(BaseModel):
        a: int

    msgs = [{"role": "user", "content": "x"}]
    assert cache_key("r", msgs, M, 0.0, "off") != cache_key("r", msgs, M, 0.0, "high")
    assert cache_key("r", msgs, M, 0.0, "off") == cache_key("r", msgs, M, 0.0, "off")
