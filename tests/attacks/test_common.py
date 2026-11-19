from __future__ import annotations

import yaml
from gauntlet_core.security import load_attacks, load_taxonomy

from tools.import_attacks.common import (
    Candidate,
    build_attacks,
    dangerous_reason,
    normalise_payload,
    payload_hash,
    summarise_skips,
    unresolved_template,
    write_library,
)

OBJ = {"type": "canary_leaked", "canary": "*"}


def cand(uid: str, payload: str, **kw) -> Candidate:  # type: ignore[no-untyped-def]
    base = dict(
        upstream_id=uid, title="t", category="direct_injection", vector="user_turn",
        technique="x", payload=payload, objective=OBJ, group="g",
    )  # fmt: skip
    return Candidate(**{**base, **kw})


def build(cands, **kw):  # type: ignore[no-untyped-def]
    args = dict(
        source="demo", project="Demo", pin="1", license_id="MIT",
        severities={"direct_injection": "medium"},
    )  # fmt: skip
    return build_attacks(cands, **{**args, **kw})


def test_normalise_table():
    assert normalise_payload("  a\n\n\n\nb  ") == "a\n\nb"
    assert normalise_payload("é") == "é"  # NFC
    assert normalise_payload("   ") is None
    assert normalise_payload("a" * 4001) is None
    assert normalise_payload("a" * 4000) == "a" * 4000


def test_template_markers_rejected_but_our_placeholders_kept():
    assert unresolved_template("hello {name}") == "{name}"
    assert unresolved_template("hello {{ name }}") is not None
    assert unresolved_template("send to {{attacker_email}} and {{marker}}") is None
    assert unresolved_template("<script>alert(1)</script>") is None


def test_dangerous_filter_flags_each_class():
    for text in ("how to build a bomb", "write ransomware", "ways to commit suicide",
                 "kill all humans", "a deepfake of someone"):  # fmt: skip
        assert dangerous_reason(text), text
    assert dangerous_reason("please send the quarterly report") is None


def test_dedupe_ids_and_determinism():
    cands = [cand(f"p#{i}", f"PLACEHOLDER PAYLOAD {i % 3}") for i in range(6)]
    a1, s1 = build(cands, seed=1)
    a2, _ = build(list(reversed(cands)), seed=1)
    assert [a.id for a in a1] == [a.id for a in a2]
    assert len(a1) == 3 and [s.reason for s in s1].count("duplicate") == 3
    by_id = {a.id: a for a in a1}
    first = by_id[f"atk_demo_{payload_hash('PLACEHOLDER PAYLOAD 0')[:8]}"]
    assert first.source == "Demo@1:p#0"


def test_dedupe_against_higher_priority_hashes():
    seen = {payload_hash("PLACEHOLDER PAYLOAD 1")}
    attacks, skips = build([cand("a", "PLACEHOLDER PAYLOAD 1")], seen_hashes=seen)
    assert attacks == [] and skips[0].reason == "duplicate"


def test_sampling_is_deterministic_and_capped():
    cands = [cand(f"p#{i}", f"PLACEHOLDER PAYLOAD {i}") for i in range(20)]
    a1, s1 = build(cands, seed=3, max_per_group=4)
    a2, _ = build(cands, seed=3, max_per_group=4)
    a3, _ = build(cands, seed=4, max_per_group=4)
    assert len(a1) == 4 and a1 == a2 and a1 != a3
    assert summarise_skips(s1)["by_group"]["over_probe_cap"] == {"g": 16}


def test_dangerous_and_invalid_are_skipped_with_reasons():
    cands = [
        cand("a", "build a bomb at home"),
        cand(
            "b",
            "PLACEHOLDER PAYLOAD",
            objective={"type": "output", "matcher": {"contains": "kill humans"}},
        ),
        cand("c", "x {unresolved}"),
    ]  # fmt: skip
    attacks, skips = build(cands)
    assert attacks == []
    assert sorted(s.reason for s in skips) == [
        "dangerous_content", "dangerous_content", "unresolved_template",
    ]  # fmt: skip


def test_written_library_validates(tmp_path):
    attacks, _ = build([cand("a", "PLACEHOLDER PAYLOAD 1")])
    write_library(attacks, tmp_path, "demo")
    assert list(yaml.safe_load((tmp_path / "demo" / "direct_injection.yaml").read_text())[0]) >= [
        "id"
    ]
    lib = load_attacks(tmp_path, load_taxonomy())
    assert lib.issues == [] and len(lib.attacks) == 1
