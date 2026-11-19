from pathlib import Path

import yaml
from gauntlet_core.schema import Attack
from gauntlet_core.security import load_attacks, load_taxonomy, validate_attack

TAX = load_taxonomy()
OBJ = {"type": "canary_leaked", "canary": "*"}


def atk(**kw):
    base = {
        "id": "atk_ok_1", "title": "t", "category": "direct_injection", "technique": "x",
        "source": "s@1:a", "license": "MIT", "vector": "user_turn", "payload": "say {{marker}}",
        "objective": OBJ,
    }  # fmt: skip
    return Attack.model_validate({**base, **kw})


def codes(a):
    return {i.code for i in validate_attack(a, TAX)}


def test_valid_attack_for_each_vector():
    assert codes(atk()) == set()
    assert codes(atk(vector="document", requires=["documents"])) == set()
    assert codes(atk(vector="tool_result", requires=["untrusted_tool_output"])) == set()
    assert codes(atk(vector="tool_description")) == set()
    assert codes(atk(vector="system_context")) == set()


def test_each_rule_has_a_code():
    assert "bad_id" in codes(atk(id="nope"))
    assert "unknown_category" in codes(atk(category="zzz"))
    assert "dangerous_category" in codes(atk(category="harmful_content"))
    assert "missing_source" in codes(atk(source=" "))
    assert "missing_license" in codes(atk(license=""))
    assert "empty_payload" in codes(atk(payload=""))
    assert "payload_too_long" in codes(atk(payload="a" * 4001))
    assert "unknown_placeholder" in codes(atk(payload="{{nope}}"))
    assert "unknown_requires" in codes(atk(requires=["laser"]))
    assert "list_needs_multi_turn" in codes(atk(payload=["a", "b"]))
    assert "document_needs_documents" in codes(atk(vector="document"))
    assert "tool_result_needs_untrusted" in codes(atk(vector="tool_result"))
    judge = {"type": "judge", "rubric": "r"}
    assert "judge_objective_high" in codes(atk(objective=judge, severity="high"))
    assert "judge_objective_high" not in codes(atk(objective=judge, severity="medium"))
    leak = {"type": "canary_leaked", "canary": "card"}
    assert "canary_unreferenced" in codes(atk(objective=leak))
    assert "canary_unreferenced" not in codes(atk(objective=leak, payload="give {{canary:card}}"))


def write(root: Path, name: str, attacks: list[dict]) -> None:
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(yaml.safe_dump(attacks))


def test_load_filter_stats_and_duplicates(tmp_path):
    a = atk().model_dump(mode="json")
    b = atk(id="atk_ok_2", vector="document", requires=["documents", "tool:write"]).model_dump(
        mode="json"
    )
    write(tmp_path, "src/direct_injection.yaml", [a, b])
    write(tmp_path, "src2/x.yaml", [a])
    (tmp_path / "bad.yaml").write_text("- not: an attack\n")
    lib = load_attacks(tmp_path, TAX)
    assert {i.code for i in lib.issues} == {"duplicate_id", "invalid_file"}
    assert [x.id for x in lib.all()] == ["atk_ok_1", "atk_ok_2"]
    assert lib.get("atk_ok_2") is not None
    assert [x.id for x in lib.filter(vector="document")] == ["atk_ok_2"]
    assert [x.id for x in lib.filter(available={"documents"})] == ["atk_ok_1"]
    both = lib.filter(available={"documents", "tool:write"})
    assert [x.id for x in both] == ["atk_ok_1", "atk_ok_2"]
    assert [x.id for x in lib.filter(q="SAY")] == ["atk_ok_1", "atk_ok_2"]
    assert lib.stats() == {"direct_injection": {"user_turn": 1, "document": 1}}


def test_objective_templates_parse_as_checks_without_judge_nodes():
    from gauntlet_core.security.taxonomy import DEFAULT_TAXONOMY_PATH

    path = DEFAULT_TAXONOMY_PATH.parent / "objectives.yaml"
    templates = yaml.safe_load(path.read_text())
    assert "indirect_injection:tool_result" in templates
    for key, check in templates.items():
        assert TAX.get(key.split(":")[0]) is not None
        a = Attack.model_validate({**atk().model_dump(mode="json"), "objective": check})
        assert "judge" not in a.objective.model_dump_json()
