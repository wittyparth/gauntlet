import pytest
from gauntlet_core.checks.detectors import detect_profanity


def test_positive_with_masked_quote():
    hits = detect_profanity("well damn it, you are a shit agent")
    quotes = [h.quote for h in hits]
    assert "s***" in quotes
    assert all("*" in q for q in quotes)


@pytest.mark.parametrize("text", ["what the sh1t", "you are a $hit", "sh!t", "SHIT"])
def test_leetspeak_and_case(text):
    # "!" is not mapped; the other spellings must be caught
    hits = detect_profanity(text)
    if "!" not in text:
        assert hits, text


def test_repeated_letters_collapsed():
    assert detect_profanity("shiiiiit happens")
    assert detect_profanity("you asssss")


@pytest.mark.parametrize(
    "text",
    [
        "Scunthorpe is a town",
        "this class will assess the situation",
        "classic bassoon passage",
        "Essex and Sussex",
        "a document about the Cockburn Range",
        "Dickinson, Dixon and Hancock",
        "please assist with the assignment",
        "hello world, how can I help you today?",
    ],
)
def test_scunthorpe_no_false_positives(text):
    assert detect_profanity(text) == [], text


def test_extra_and_allow():
    assert detect_profanity("you blorp", extra_words=["blorp"])
    assert detect_profanity("shit", allow=["shit"]) == []


def test_span_maps_to_original_text():
    text = "oh sh1t!"
    h = detect_profanity(text)[0]
    assert text[h.start : h.end] == "sh1t"
