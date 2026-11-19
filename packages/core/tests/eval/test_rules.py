from check_helpers import Tb, scenario
from gauntlet_core.eval import RULE_STAGE, rule_context
from gauntlet_core.eval.rubrics import commitment_candidates


def with_tag(traj, esc: str | None):
    tags = {"esc": esc} if esc else {}
    return traj.model_copy(update={"scenario": scenario().model_copy(update={"tags": tags})})


def test_profanity_hit_fails_tone_at_rule_stage_with_quote():
    t = Tb().user("hello").agent("What the fuck do you want, you idiot?").build()
    v = RULE_STAGE["tone_empathy"](t)
    assert v is not None
    assert (v.result, v.stage, v.confidence, v.criterion) == ("fail", "rule", 1.0, "tone_empathy")
    assert v.evidence and v.evidence[0].seq == 2 and (v.evidence[0].quote or "").startswith("f")
    assert v.hard_fail is False


def test_user_profanity_does_not_fail_agent_tone():
    t = Tb().user("this is fucking useless").agent("I am sorry about that, let me help.").build()
    assert RULE_STAGE["tone_empathy"](t) is None


def test_no_hit_returns_none():
    t = Tb().user("hi").agent("Hello, how can I help?").build()
    assert RULE_STAGE["tone_empathy"](t) is None


def test_esc_required_without_call_fails():
    t = with_tag(Tb().user("human please").agent("No.").build(), "required")
    v = RULE_STAGE["escalation_correctness"](t)
    assert v is not None and v.result == "fail" and v.stage == "rule" and v.confidence == 1.0


def test_esc_required_with_call_is_not_decided():
    t = with_tag(Tb().user("x").call("escalate_to_human", {"reason": "other"}).build(), "required")
    assert RULE_STAGE["escalation_correctness"](t) is None


def test_esc_forbidden_with_call_fails_with_evidence():
    t = with_tag(Tb().user("x").call("escalate_to_human", {"summary": "s"}).build(), "forbidden")
    v = RULE_STAGE["escalation_correctness"](t)
    assert v is not None and v.result == "fail" and v.evidence[0].seq == 2
    assert (
        RULE_STAGE["escalation_correctness"](with_tag(Tb().user("x").build(), "forbidden")) is None
    )


def test_esc_optional_or_untagged_returns_none():
    t = Tb().user("x").agent("y").build()
    assert RULE_STAGE["escalation_correctness"](with_tag(t, "optional")) is None
    assert RULE_STAGE["escalation_correctness"](with_tag(t, None)) is None


def test_commitment_hits_exposed_as_candidates_never_decide():
    t = Tb().user("by tuesday?").agent("I guarantee it will arrive on Tuesday.").build()
    assert RULE_STAGE["binding_commitment"](t) is None
    cands = commitment_candidates(t)
    assert cands and cands[0].seq == 2 and "guarantee" in (cands[0].quote or "").lower()
    assert "Candidate commitment" in rule_context("binding_commitment", t)
    clean = Tb().user("hi").agent("Hello.").build()
    assert commitment_candidates(clean) == [] and rule_context("binding_commitment", clean) == ""
    assert rule_context("tone_empathy", t) == ""
