from gauntlet_core.sim import load_persona_library

IDS = [
    "per_cooperative",
    "per_impatient",
    "per_confused_novice",
    "per_angry_escalator",
    "per_storyteller",
    "per_terse_typo",
    "per_persistent_negotiator",
    "per_social_engineer",
    "per_refund_abuser",
    "per_code_switcher",
]


def test_ten_personas_with_stable_ids():
    lib = load_persona_library()
    assert list(lib) == IDS
    assert all(k == p.id for k, p in lib.items())


def test_core_traits_and_rule_counts():
    for p in load_persona_library().values():
        assert {"patience", "literacy", "emotion", "verbosity"} <= set(p.traits), p.id
        assert isinstance(p.traits["patience"], float) and isinstance(p.traits["literacy"], float)
        assert isinstance(p.traits["emotion"], str) and isinstance(p.traits["verbosity"], str)
        assert 2 <= len(p.behavior_rules) <= 4, p.id


def test_adversarial_ids_exact():
    adv = {i for i, p in load_persona_library().items() if p.adversarial_intent}
    assert adv == {"per_social_engineer", "per_refund_abuser", "per_persistent_negotiator"}


def test_typo_persona_has_rate():
    assert load_persona_library()["per_terse_typo"].traits["typo_rate"] == 0.12
