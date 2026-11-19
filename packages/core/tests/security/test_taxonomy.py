import re

from gauntlet_core.security import load_taxonomy


def test_seventeen_categories_numbered_and_unique():
    t = load_taxonomy()
    assert [c.number for c in t.categories] == list(range(1, 18))
    assert len(set(t.ids())) == 17


def test_only_harmful_content_is_dangerous():
    assert [c.id for c in load_taxonomy().categories if c.dangerous] == ["harmful_content"]


def test_framework_ids_have_valid_shape_and_header_is_verified():
    t = load_taxonomy()
    assert re.match(r"\d{4}-\d{2}-\d{2}", t.verified_on)
    assert {"owasp_llm", "owasp_agentic", "atlas"} <= set(t.sources)
    for c in t.categories:
        assert all(re.fullmatch(r"LLM(0[1-9]|10)", o) for o in c.owasp_llm)
        assert all(re.fullmatch(r"T([1-9]|1[0-7])", o) for o in c.owasp_agentic)
        assert all(re.fullmatch(r"AML\.T\d{4}(\.\d{3})?", o) for o in c.atlas)


def test_owasp_index_and_get():
    t = load_taxonomy()
    assert "direct_injection" in t.owasp_index()["LLM01"]
    assert t.get("nope") is None
