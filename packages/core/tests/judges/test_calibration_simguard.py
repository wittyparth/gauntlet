import re

from gauntlet_core.judges import (
    GoldenItem,
    SimulatorGuard,
    calibrate,
    calibrated,
    evaluate_sim_fidelity,
)
from gauntlet_core.llm import FakeLLM
from judge_helpers import Tb, reply, rubric

S, T = "judge_small", "judge_strong"


def golden(n: int) -> list[GoldenItem]:
    items = []
    for i in range(n):
        t = Tb().user("hello").agent(f"ITEM-{i:03d} refund approved without checking").build()
        items.append(GoldenItem(f"g{i}", t, "fail" if i % 2 == 0 else "pass"))
    return items


def judge(correct_conf: float, hard_conf: float | None):
    """A judge that is right on easy items; on every third item it is wrong with `hard_conf`."""

    def fn(messages):
        m = re.search(r"ITEM-(\d+)", messages[1]["content"])
        assert m is not None
        i = int(m.group(1))
        truth_fail = i % 2 == 0
        wrong = hard_conf is not None and i % 3 == 0
        says_fail = truth_fail != wrong
        conf = hard_conf if wrong and hard_conf is not None else correct_conf
        ev = [(2, f"ITEM-{i:03d} refund approved without")] if says_fail else []
        return reply("fail" if says_fail else "pass", conf, ev, usd=5)

    return fn


async def test_calibration_recovers_expected_tau_and_gates():
    n = 60
    f = FakeLLM(by_role={S: [judge(0.95, 0.6)] * n, T: [judge(0.9, None)] * n})
    r = rubric()
    rep = await calibrate(r, golden(n), f, resamples=100)
    f.assert_consumed()
    assert rep.threshold == 0.7  # wrong small answers have confidence 0.6
    by_tau = {p.tau: p for p in rep.points}
    a6, a7 = by_tau[0.6].agreement, by_tau[0.7].agreement
    assert a6 is not None and a7 is not None
    assert a6.kappa < 0.9 and a7.kappa == 1.0
    assert by_tau[0.5].escalation_rate == 0 and 0.3 < by_tau[0.7].escalation_rate < 0.4
    assert by_tau[0.7].cost_per_verdict_usd_micros > by_tau[0.5].cost_per_verdict_usd_micros
    assert rep.strong is not None and rep.small is not None
    assert rep.strong.kappa == 1.0 and rep.small.kappa < 1.0
    assert rep.gating_allowed and rep.gating_reason == "ok"
    c = calibrated(r, rep)
    assert c.threshold == 0.7 and c.gating_allowed


async def test_gating_requires_enough_labelled_items_per_class():
    n = 20
    f = FakeLLM(by_role={S: [judge(0.95, None)] * n, T: [judge(0.9, None)] * n})
    rep = await calibrate(rubric(), golden(n), f, resamples=50)
    assert not rep.gating_allowed and "labelled items" in rep.gating_reason
    f2 = FakeLLM(by_role={S: [judge(0.95, None)] * 45, T: [judge(0.9, None)] * 45})
    skew = golden(45)
    skew = [GoldenItem(g.id, g.trajectory, "pass" if i % 9 else "fail") for i, g in enumerate(skew)]
    f2 = FakeLLM(by_role={S: [reply("pass", 0.9)] * 45, T: [reply("pass", 0.9)] * 45})
    rep2 = await calibrate(rubric(), skew, f2, resamples=50)
    assert not rep2.gating_allowed and "classes" in rep2.gating_reason


async def test_gating_requires_strong_kappa():
    n = 50
    noisy = judge(0.9, 0.9)  # wrong on every third item with high confidence
    f = FakeLLM(by_role={S: [noisy] * n, T: [lambda m: reply("pass", 0.9)] * n})
    rep = await calibrate(rubric(), golden(n), f, resamples=50)
    assert not rep.gating_allowed and "kappa" in rep.gating_reason


def test_sim_guard_rules():
    g = SimulatorGuard(hidden_facts=["order number is ORD-48213 placed on Monday"])

    def code(guard, text, agent=()):
        issue = guard.check(text, list(agent))
        return issue.code if issue else None

    assert code(g, "") == "empty"
    assert code(g, "As an AI I can help with that") == "claims_assistant"
    assert code(g, "How can I help you today?") == "claims_assistant"
    assert code(g, "Здравствуйте, мне нужен возврат денег") == "language_switch"
    assert code(g, "my order is ORD-48213") == "hidden_fact_early"
    assert code(g, "my order is ORD-48213", ["What is your order number?"]) is None
    assert code(g, "I need a refund please") is None
    ja = SimulatorGuard(persona_language="ja")
    assert code(ja, "返金をお願いします") is None
    assert code(ja, "I want a refund") == "language_switch"


async def test_sim_fidelity_uses_small_judge_only_and_sees_persona():
    t = Tb().user("hello, I am angry").agent("how can I help").build()
    f = FakeLLM(by_role={S: [reply("pass", 0.3)], T: []})
    v = await evaluate_sim_fidelity(t, f, "Persona: Grumpy Gary. Goal: refund")
    assert v.criterion == "simulator_fidelity" and v.stage == "small" and v.result == "pass"
    assert "Grumpy Gary" in f.calls[0].messages[1]["content"]
    assert [c.role for c in f.calls] == [S]
