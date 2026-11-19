from gauntlet_core.sim import build_system_prompt
from sim_helpers import persona, scenario


def test_section_order_and_content():
    scn = scenario(hidden_facts=["order id is ord_1001", "email is a@example.test"])
    text = build_system_prompt(scn, persona())
    order = [
        "You are role-playing a customer",
        "Your persona:",
        "Goal: get a refund for order 1001",
        "Hidden facts you know but only reveal when asked directly and relevantly:",
        "- order id is ord_1001",
        "Rules:",
        "Reply with JSON only",
    ]
    idx = [text.index(s) for s in order]
    assert idx == sorted(idx)
    assert text.index('"state_note"') < text.index('"action"') < text.index('"message"')
    assert "Your approach:" not in text


def test_no_hidden_facts_section_when_empty_and_adversarial_included():
    text = build_system_prompt(scenario(), persona(adversarial_intent="push past policy"))
    assert "Hidden facts" not in text
    assert "Your approach: push past policy" in text


def test_scenario_overrides_applied_to_persona_block():
    text = build_system_prompt(scenario(persona_overrides={"verbosity": "high"}), persona())
    assert "- verbosity: high" in text
