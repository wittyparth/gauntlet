import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "checks"))

from check_helpers import Tb
from gauntlet_core.mining import anonymise

RAW = [
    "Hi, my name is Maria Gonzalez and I live at 42 Maple Street.",
    "Please check order ORD-4417, my email is [EMAIL_a1b2c3] and phone [PHONE_00aa11].",
    "Thanks, Maria Gonzalez, account 88231 is fine; card [CARD_ffeedd] on file.",
]


def conv() -> Tb:
    tb = Tb()
    tb.user(RAW[0]).agent(RAW[1]).user(RAW[2])
    tb.call(
        "lookup_order",
        {"order_id": "ORD-4417", "who": "Maria Gonzalez"},
        result='{"id": "ORD-4417"}',
    )
    return tb


def blob(a) -> str:
    return str([e.payload for e in a.events])


def test_planted_values_are_replaced():
    a = anonymise(conv().events, seed=1)
    text = blob(a)
    for gone in ("Maria Gonzalez", "42 Maple Street", "4417", "88231", "[EMAIL_a1b2c3]",
                 "[PHONE_00aa11]", "[CARD_ffeedd]"):  # fmt: skip
        assert gone not in text, gone
    assert a.replacements >= 8 and a.residual == []
    assert "@example.test" in text and "[phone on file]" in text and "[card on file]" in text


def test_consistent_within_and_across_conversations_for_one_seed():
    a, b = anonymise(conv().events, seed=1), anonymise(conv().events, seed=1)
    assert blob(a) == blob(b) and a.mapping_hash == b.mapping_hash
    # the same order id gets the same stand-in everywhere it appears, including tool args
    call = next(e for e in a.events if e.kind == "tool_call").payload
    result = next(e for e in a.events if e.kind == "tool_result").payload["result"]
    assert (
        call["args"]["order_id"].lower().startswith("ord-")
        and call["args"]["order_id"][4:] in result
    )
    assert call["args"]["who"] != "Maria Gonzalez"
    names = {call["args"]["who"], *[w for w in blob(a).split("'") if w == call["args"]["who"]]}
    assert len(names) == 1


def test_different_seeds_give_different_stand_ins():
    assert blob(anonymise(conv().events, seed=1)) != blob(anonymise(conv().events, seed=2))
    assert (
        anonymise(conv().events, seed=1).mapping_hash
        != anonymise(conv().events, seed=2).mapping_hash
    )


def test_idempotent_enough_second_pass_finds_nothing_new():
    first = anonymise(conv().events, seed=1)
    second = anonymise(first.events, seed=1)
    assert second.residual == [] and "Maria" not in blob(second)


def test_residual_lists_what_could_not_be_replaced():
    tb = Tb().user("my key is AKIAIOSFODNN7EXAMPLE and token Zx9Qm2Lp7Rt4Vb8Nc3Kd5Hs1")
    a = anonymise(tb.events, seed=1)
    kinds = {r.kind for r in a.residual}
    assert "secret" in kinds
    tb2 = Tb().user("call 415-555-0132 or see [EMAIL_zzzzzz]")  # a malformed token is not ours
    assert {r.kind for r in anonymise(tb2.events, seed=1).residual} >= {"phone"}
    # residual values stay out of repr
    assert "AKIA" not in repr(a.residual)


def test_non_person_greetings_are_left_alone():
    tb = Tb().user("Thanks Please help").agent("Hello there")
    assert blob(anonymise(tb.events, seed=1)) == blob(type("A", (), {"events": tb.events})())
