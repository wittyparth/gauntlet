from __future__ import annotations

from pathlib import Path

from gauntlet_core.security import load_taxonomy, validate_attack

from tools.import_attacks import injecagent
from tools.import_attacks.common import build_attacks, load_mapping

FIX = Path(__file__).parent / "fixtures" / "injecagent"


def run():  # type: ignore[no-untyped-def]
    cands, skips = injecagent.read_candidates(FIX)
    m = load_mapping("injecagent")
    attacks, more = build_attacks(
        cands, source="injecagent", project=m["project"], pin="abc", license_id=m["license"],
        severities=m["severity"], max_per_group=40,
    )  # fmt: skip
    return attacks, [*skips, *more]


def test_parses_maps_and_validates():
    attacks, _ = run()
    tax = load_taxonomy()
    assert all(validate_attack(a, tax) == [] for a in attacks)
    by_cat = {a.category: a for a in attacks}
    assert by_cat["indirect_injection"].vector == "tool_result"
    assert by_cat["exfiltration"].requires == ["untrusted_tool_output", "tool:external_comm"]
    assert by_cat["indirect_injection"].source.startswith("InjecAgent@abc:direct_harm:")
    assert {a.license for a in attacks} == {"MIT"}


def test_excludes_physical_harm_and_upstream_tool_names():
    attacks, skips = run()
    reasons = {s.upstream_id: s.reason for s in skips}
    assert reasons["direct_harm:1"] == "excluded_type"
    assert reasons["direct_harm:2"] == "upstream_tool_name"
    assert len(attacks) == 2


def test_substitutes_attacker_email():
    attacks, _ = run()
    ds = next(a for a in attacks if a.category == "exfiltration")
    assert ds.payload == "PLACEHOLDER PAYLOAD 4 send it to {{attacker_email}}"
