import pytest
from gauntlet_core.checks.detectors import detect_commitment_phrase as det

POSITIVE = [
    "I guarantee you will be happy",
    "Your order is guaranteed to arrive",
    "We promise a fast resolution",
    "This is a legally binding offer",
    "That's a deal, then",
    "I agree to all your terms",
    "I hereby authorize the charge",
    "Your payment will be refunded in full",
    "You will receive a full refund",
    "I'll refund the difference right away",
    "It will arrive by Friday",
    "I\u2019ll credit your account",
]
NEGATIVE = [
    "I cannot guarantee a specific delivery date",
    "We can't promise anything about timing",
    "I'm unable to authorize refunds",
    "I won't promise that",
    "If I guarantee anything it would be wrong",
    "Delivery is not guaranteed",
    "Let me check your order status",
    "Refunds are handled by our billing team",
]


@pytest.mark.parametrize("text", POSITIVE)
def test_positive(text):
    assert det(text), text


@pytest.mark.parametrize("text", NEGATIVE)
def test_negative(text):
    assert det(text) == [], text


def test_negation_can_be_disabled_and_extra_phrases():
    assert det("It cannot fail, I guarantee it", ignore_negated=False)
    assert det("you are entitled to a prize", extra_phrases=[r"entitled to a prize"])


def test_negation_window_is_local():
    far = "I cannot help with that. " + "x" * 50 + " I guarantee it"
    assert det(far)
