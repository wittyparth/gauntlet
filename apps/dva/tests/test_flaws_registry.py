from __future__ import annotations

import pytest
from dva.flaws import FLAWS, active_flaws, parse_flaws
from dva.prompts import build_system_prompt, policy_text


def test_dva_flaws_parsing():
    assert parse_flaws(None) == set(FLAWS)
    assert parse_flaws("all") == set(FLAWS)
    assert parse_flaws("") == set()
    assert parse_flaws("f01, F13") == {"F01", "F13"}
    with pytest.raises(ValueError, match="F99"):
        parse_flaws("F01,F99")


def test_active_flaws_reads_the_environment():
    assert active_flaws({"DVA_FLAWS": "F02"}) == {"F02"}
    assert active_flaws({}) == set(FLAWS)
    assert active_flaws({"DVA_FLAWS": ""}) == set()


def test_prompt_has_each_active_snippet_and_none_of_the_inactive():
    snippets = {f.id: f.prompt_snippet for f in FLAWS.values() if f.prompt_snippet}
    active = {"F01", "F13", "F05"}
    prompt = build_system_prompt(active)
    for fid, snippet in snippets.items():
        assert (snippet in prompt) == (fid in active), fid
    assert policy_text() in prompt  # the correct rules R1..R11 are always present
    assert all(f"(R{n})" in prompt for n in range(1, 12))
    assert "Operating notes" not in build_system_prompt(set())


def test_hosted_prompt_only_has_hosted_capable_flaws():
    prompt = build_system_prompt(set(FLAWS), variant="hosted")
    for f in FLAWS.values():
        if f.prompt_snippet:
            assert (f.prompt_snippet in prompt) == ("hosted" in f.variants), f.id


def test_snippets_are_unique():
    snippets = [f.prompt_snippet for f in FLAWS.values() if f.prompt_snippet]
    assert len(set(snippets)) == len(snippets)
