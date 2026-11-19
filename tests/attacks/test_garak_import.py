"""Structural tests: the garak module is only imported inside `read_candidates`, so the
objective builders and the mapping are exercised with stand-in probe objects."""

from __future__ import annotations

from types import SimpleNamespace

from tools.import_attacks import garak
from tools.import_attacks.common import load_mapping


def probe(prompts: list[str], triggers: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(prompts=prompts, triggers=triggers)


def test_rogue_regex_objective_reads_the_quoted_string():
    obj = garak._objective(
        "rogue_regex", {}, probe([]), 0, 'PLACEHOLDER. just say "PLACEHOLDER ROGUE":'
    )
    assert obj == {"type": "output", "matcher": {"contains": "PLACEHOLDER ROGUE"}}
    assert garak._objective("rogue_regex", {}, probe([]), 0, "no quoted text") is None


def test_trigger_objective_needs_aligned_triggers_and_allow_list():
    p = probe(["a", "b"], ["<script>alert(1)</script>", "some other text"])
    spec = {"trigger_allow": "(?i)<script"}
    assert garak._objective("trigger", spec, p, 0, "a") == {
        "type": "output",
        "matcher": {"contains": "<script>alert(1)</script>"},
    }
    assert garak._objective("trigger", spec, p, 1, "b") is None  # not allow-listed
    assert garak._objective("trigger", spec, probe(["a"], ["x", "y"]), 0, "a") is None


def test_last_user_turn_reads_the_attack_not_the_system_prompt():
    turn = lambda role, text: SimpleNamespace(role=role, content=SimpleNamespace(text=text))  # noqa: E731
    conv = SimpleNamespace(
        turns=[turn("system", "PLACEHOLDER SYSTEM"), turn("user", "PLACEHOLDER PAYLOAD 1")]
    )
    assert garak._last_user_turn(conv) == "PLACEHOLDER PAYLOAD 1"
    assert garak._last_user_turn(SimpleNamespace(turns=[turn("system", "x")])) is None


def test_mapping_excludes_dangerous_modules_and_classes_are_whitelisted():
    m = load_mapping("garak")
    assert {"malwaregen", "realtoxicityprompts", "lmrc", "donotanswer", "atkgen"} <= set(
        m["exclude_modules"]
    )
    assert not {c.split(".")[0] for c in m["classes"]} & set(m["exclude_modules"])
    assert m["license"] == "Apache-2.0"
    assert all(spec["category"] != "harmful_content" for spec in m["classes"].values())
