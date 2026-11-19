from __future__ import annotations

from pathlib import Path

from gauntlet_core.security import load_taxonomy, validate_attack

from tools.import_attacks import promptfoo
from tools.import_attacks.common import build_attacks, load_mapping

FIX = Path(__file__).parent / "fixtures" / "promptfoo"


def run():  # type: ignore[no-untyped-def]
    cands, skips = promptfoo.read_candidates(FIX)
    m = load_mapping("promptfoo")
    attacks, more = build_attacks(
        cands, source="promptfoo", project=m["project"], pin="abc", license_id=m["license"],
        severities=m["severity"],
    )  # fmt: skip
    return attacks, [*skips, *more]


def test_extracts_only_example_prompts():
    src = (FIX / "src/redteam/plugins/promptExtraction.ts").read_text()
    assert promptfoo.extract_examples(src) == [
        "PLACEHOLDER PAYLOAD 1",
        "PLACEHOLDER PAYLOAD 2 with {{name}}",
    ]


def test_maps_validates_and_skips_templates():
    attacks, skips = run()
    tax = load_taxonomy()
    assert all(validate_attack(a, tax) == [] for a in attacks)
    assert {a.category for a in attacks} == {"prompt_extraction", "tool_injection"}
    assert any(s.reason == "unresolved_template" for s in skips)
    assert all("@abc:" in a.source and a.license == "MIT" for a in attacks)


def test_excluded_plugins_are_recorded_and_never_read():
    _, skips = run()
    excluded = {s.upstream_id for s in skips if s.reason == "excluded_plugin"}
    assert {"harmful", "beavertails", "pliny", "toxicity", "hate", "self-harm"} <= excluded


def test_unescapes_and_replaces_attacker_url():
    attacks, _ = run()
    shell = next(a for a in attacks if a.category == "tool_injection")
    assert "{{attacker_url}}" in shell.payload and "evil.com" not in shell.payload
