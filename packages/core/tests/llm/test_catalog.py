import pytest
from gauntlet_core.llm import GatewayConfig
from gauntlet_core.llm.catalog import (
    CATALOG,
    SETTABLE_ROLES,
    RoleChoice,
    apply_role_settings,
    catalog_model,
)


def test_catalog_has_no_openai_or_anthropic_models():
    assert len(CATALOG) >= 6
    for m in CATALOG:
        assert m.id.startswith("openrouter/")
        assert not m.id.removeprefix("openrouter/").startswith(("openai/", "anthropic/", "~"))
        assert "openai" not in m.provider_family.lower()
        assert "anthropic" not in m.provider_family.lower()


def test_catalog_entries_are_complete_and_cheap():
    ids = [m.id for m in CATALOG]
    assert len(ids) == len(set(ids))
    for m in CATALOG:
        assert m.name and m.description and m.good_for and m.recommended_roles
        assert m.context_length > 0
        assert 0 < m.input_usd_per_mtok <= 0.5 and 0 < m.output_usd_per_mtok <= 1.0
        assert set(m.recommended_roles) <= set(SETTABLE_ROLES)


def test_default_role_models_are_in_the_catalog():
    cfg = GatewayConfig()
    for role in SETTABLE_ROLES:
        assert catalog_model(cfg.llm.roles[role].model) is not None, role


def test_catalog_model_lookup():
    assert catalog_model("openrouter/qwen/qwen3.7-flash") is not None
    assert catalog_model("openai/gpt-4o") is None


def test_apply_role_settings_overrides_model_and_reasoning_without_mutating():
    base = GatewayConfig()
    out = apply_role_settings(
        base, {"judge_strong": RoleChoice(model="openrouter/qwen/qwen3.8-flash", reasoning="low")}
    )
    assert out.llm.roles["judge_strong"].model == "openrouter/qwen/qwen3.8-flash"
    assert out.llm.roles["judge_strong"].reasoning == "low"
    assert out.llm.roles["judge_strong"].max_output_tokens == 2048  # other fields kept
    assert base.llm.roles["judge_strong"].model != "openrouter/qwen/qwen3.8-flash"
    assert "openrouter/qwen/qwen3.8-flash" in out.llm.pricing  # priced from the catalog


def test_apply_role_settings_ignores_unknown_roles():
    with pytest.raises(ValueError):
        apply_role_settings(GatewayConfig(), {"embedder": RoleChoice(model="x", reasoning="off")})
