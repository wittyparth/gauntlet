from gauntlet_core.policy.compile import split_clauses
from gauntlet_core.policy.compile.clauses import MAX_CLAUSE


def texts(s: str) -> list[str]:
    return [c.text for c in split_clauses(s)]


def test_numbered_items_with_continuation_and_preamble():
    src = (
        "# Title\n\nYou are an assistant.\n\n1. **A.** First rule\n   continues here.\n2. Second.\n"
    )
    cs = split_clauses(src)
    assert [c.text for c in cs] == ["**A.** First rule continues here.", "Second."]
    assert [c.id for c in cs] == ["c01", "c02"]
    s, e = cs[1].source_span
    assert src[s:e] == "Second."


def test_bulleted():
    assert texts("- one\n* two\n• three\n") == ["one", "two", "three"]


def test_paragraphs_when_no_list():
    assert texts("First para\nstill first.\n\nSecond para.\n") == [
        "First para still first.",
        "Second para.",
    ]


def test_long_clause_splits_on_sentences_and_stays_in_order():
    sentence = "This is a fairly long sentence that says something about policy. "
    long = sentence * 12  # about 770 chars
    cs = split_clauses("1. " + long.strip() + "\n2. Short.\n")
    assert len(cs) >= 3 and all(len(c.text) <= MAX_CLAUSE + len(sentence) for c in cs)
    assert " ".join(c.text for c in cs[:-1]).replace("  ", " ") == long.strip()
    assert cs[-1].text == "Short."


def test_short_multi_sentence_clause_stays_together():
    assert texts("1. One. Two. Three.\n") == ["One. Two. Three."]


def test_ids_stable_across_calls():
    src = "1. a\n2. b\n3. c\n"
    assert [c.id for c in split_clauses(src)] == [c.id for c in split_clauses(src)]
    assert split_clauses("") == []
