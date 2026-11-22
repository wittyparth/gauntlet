import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "checks"))

from check_helpers import Tb
from gauntlet_core.mining import signals


def ev(tb: Tb):
    return tb.events


def test_rephrasing():
    tb = (
        Tb()
        .user("where is my order ord_1")
        .agent("it shipped")
        .user("where is my order ord_1 please")
    )
    value, why = signals.rephrasing(ev(tb))
    assert value == 0.5 and why
    tb2 = Tb().user("where is my order").agent("ok").user("also cancel the subscription now")
    assert signals.rephrasing(ev(tb2)) == (0.0, [])
    twice = Tb().user("fix my login problem now").agent("a").user("fix my login problem now")
    twice.agent("b").user("fix my login problem now")
    assert signals.rephrasing(ev(twice))[0] == 1.0


def test_dissatisfaction_and_human_request():
    tb = (
        Tb()
        .user("this is useless, you're not listening")
        .agent("sorry")
        .user("I want to talk to a human")
    )
    assert signals.dissatisfaction(ev(tb))[0] == 0.5
    assert signals.human_request(ev(tb))[0] == 0.6
    calm = Tb().user("thanks, that helped").agent("great")
    assert signals.dissatisfaction(ev(calm))[0] == 0 and signals.human_request(ev(calm))[0] == 0
    assert signals.human_request(ev(Tb().user("get me a real person")))[0] == 0.6


def test_abandonment():
    assert (
        signals.abandonment(ev(Tb().user("hello").agent("hi").user("my card was charged twice")))[0]
        == 0.5
    )
    assert (
        signals.abandonment(ev(Tb().user("refund?").agent("Sorry, I cannot help with that.")))[0]
        == 0.4
    )
    resolved = Tb().user("a").agent("b").user("c").agent("d").user("e").agent("Sorry about that")
    assert signals.abandonment(ev(resolved))[0] == 0.0  # not an early apology
    assert signals.abandonment([]) == (0.0, [])


def test_redaction_leak_only_from_agent_output():
    leak = Tb().user("hi").agent("Your card is [CARD_a1b2c3] and key [SECRET_00ff00]")
    value, why = signals.redaction_leak(ev(leak))
    assert value == 1.0 and "card, secret" in why[0]
    echo = Tb().user("my card is [CARD_a1b2c3]").agent("thanks, noted")
    assert signals.redaction_leak(ev(echo)) == (0.0, [])
    email_only = Tb().agent("write to [EMAIL_abcdef]")
    assert signals.redaction_leak(ev(email_only)) == (0.0, [])
