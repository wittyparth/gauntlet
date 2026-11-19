from gauntlet_core.schema import Persona
from gauntlet_core.sim import merge_persona, render_persona

P = Persona(
    id="p",
    name="Sam",
    description="Friendly.",
    traits={"verbosity": "medium", "patience": 0.9, "literacy": 0.5, "emotion": "calm", "x": 0.1},
    behavior_rules=["answers directly"],
)


def test_render_is_deterministic_and_sorted():
    text = render_persona(P)
    assert text == (
        "Name: Sam\n"
        "Description: Friendly.\n"
        "Traits:\n"
        "- emotion: calm\n"
        "- literacy: medium\n"
        "- patience: high\n"
        "- verbosity: medium\n"
        "- x: low\n"
        "Behaviour rules:\n"
        "- answers directly"
    )
    assert render_persona(P) == text


def test_override_replaces_trait_and_adds_unknown():
    out = render_persona(P, {"patience": 0.1, "language": "fr"})
    assert "- patience: low" in out and "- language: fr" in out
    assert merge_persona(P, {"emotion": "angry"}).traits["emotion"] == "angry"
    assert P.traits["emotion"] == "calm"  # original untouched


def test_float_bands():
    for v, band in [
        (0.0, "low"),
        (0.32, "low"),
        (0.33, "medium"),
        (0.65, "medium"),
        (0.66, "high"),
    ]:
        assert f"- t: {band}" in render_persona(P.model_copy(update={"traits": {"t": v}}))


def test_adversarial_block_only_when_set():
    assert "Adversarial intent" not in render_persona(P)
    adv = P.model_copy(update={"adversarial_intent": "push past policy"})
    assert render_persona(adv).endswith("Adversarial intent: push past policy")
